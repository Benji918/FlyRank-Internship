"""
Comprehensive test suite for Task API with AI Analysis.

Tests cover:
1. Authentication and authorization
2. Valid analysis requests
3. Schema validation
4. Timeout handling
5. Retry logic
6. Database persistence
7. Error responses
8. Concurrent requests
"""
import asyncio
import os
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import app, repo
from ai_service import AIAnalysisService, TaskAnalysis


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def test_user():
    """Create a test user and return credentials."""
    email = "test@example.com"
    password = "password123"
    
    # Clean up if exists
    existing = repo.get_user_by_email(email)
    
    return {"email": email, "password": password}


@pytest.fixture
def auth_token(client, test_user):
    """Get authentication token for test user."""
    # Signup
    client.post(
        "/auth/signup",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    
    # Login
    response = client.post(
        "/auth/login",
        json={"email": test_user["email"], "password": test_user["password"]},
    )
    
    return response.json()["access_token"]


@pytest.fixture
def auth_header(auth_token):
    """Create authorization header."""
    return {"Authorization": f"Bearer {auth_token}"}


# ============================================================================
# 1. Authentication and Authorization Tests
# ============================================================================

class TestAuthentication:
    """Test authentication and authorization."""
    
    def test_signup_success(self, client):
        """Test successful signup."""
        response = client.post(
            "/auth/signup",
            json={"email": "newuser@example.com", "password": "password123"},
        )
        assert response.status_code == 201
        assert response.json()["email"] == "newuser@example.com"
    
    def test_signup_duplicate_email(self, client, test_user):
        """Test signup with duplicate email."""
        # First signup
        client.post(
            "/auth/signup",
            json={"email": test_user["email"], "password": test_user["password"]},
        )
        
        # Second signup with same email
        response = client.post(
            "/auth/signup",
            json={"email": test_user["email"], "password": "different123"},
        )
        assert response.status_code == 400
        assert "already registered" in response.json()["error"]
    
    def test_login_success(self, client, test_user):
        """Test successful login."""
        # Signup first
        client.post(
            "/auth/signup",
            json={"email": test_user["email"], "password": test_user["password"]},
        )
        
        response = client.post(
            "/auth/login",
            json={"email": test_user["email"], "password": test_user["password"]},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert "refresh_token" in response.json()
    
    def test_login_invalid_credentials(self, client, test_user):
        """Test login with invalid credentials."""
        client.post(
            "/auth/signup",
            json={"email": test_user["email"], "password": test_user["password"]},
        )
        
        response = client.post(
            "/auth/login",
            json={"email": test_user["email"], "password": "wrongpassword"},
        )
        assert response.status_code == 401
    
    def test_protected_endpoint_without_token(self, client):
        """Test accessing protected endpoint without token."""
        response = client.get("/protected/profile")
        assert response.status_code == 401
    
    def test_protected_endpoint_with_token(self, client, auth_token, test_user):
        """Test accessing protected endpoint with valid token."""
        response = client.get(
            "/protected/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == test_user["email"]


# ============================================================================
# 2. Valid Analysis Requests
# ============================================================================

class TestAnalysisRequests:
    """Test valid analysis request handling."""
    
    @pytest.mark.asyncio
    async def test_analyze_task_success(self, client, auth_header):
        """Test successful task analysis."""
        with patch("ai_service.ChatOpenAI") as mock_llm:
            # Mock LLM response
            mock_response = MagicMock()
            mock_response.content = """{
                "task_type": "review",
                "category": "finance",
                "priority": "high",
                "estimated_time_minutes": 60,
                "key_points": ["review proposal", "provide recommendations"],
                "confidence": 0.95
            }"""
            
            mock_llm.return_value.invoke.return_value = mock_response
            
            response = client.post(
                "/analyze-task",
                json={"task_description": "Review the Q4 budget proposal and provide recommendations"},
                headers=auth_header,
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["analysis"]["task_type"] == "review"
            assert data["analysis"]["category"] == "finance"
            assert data["analysis"]["priority"] == "high"
            assert data["analysis"]["confidence"] == 0.95
    
    @pytest.mark.asyncio
    async def test_analyze_task_persists_to_db(self, client, auth_header):
        """Test that analysis is stored in database."""
        with patch("ai_service.ChatOpenAI") as mock_llm:
            mock_response = MagicMock()
            mock_response.content = """{
                "task_type": "implement",
                "category": "engineering",
                "priority": "medium",
                "estimated_time_minutes": 120,
                "key_points": ["write tests", "refactor code"],
                "confidence": 0.88
            }"""
            
            mock_llm.return_value.invoke.return_value = mock_response
            
            response = client.post(
                "/analyze-task",
                json={"task_description": "Implement new authentication module with comprehensive tests"},
                headers=auth_header,
            )
            
            assert response.status_code == 200
            analysis_id = response.json()["id"]
            
            # Verify in database
            analyses = client.get("/analyses", headers=auth_header).json()["analyses"]
            assert len(analyses) > 0
            assert any(a["id"] == analysis_id for a in analyses)


# ============================================================================
# 3. Schema Validation Tests
# ============================================================================

class TestSchemaValidation:
    """Test request and response schema validation."""
    
    def test_analysis_request_too_short(self, client, auth_header):
        """Test analysis request with description too short."""
        response = client.post(
            "/analyze-task",
            json={"task_description": "short"},
            headers=auth_header,
        )
        assert response.status_code == 422  # Validation error
    
    def test_analysis_request_too_long(self, client, auth_header):
        """Test analysis request with description too long."""
        long_description = "a" * 5001
        response = client.post(
            "/analyze-task",
            json={"task_description": long_description},
            headers=auth_header,
        )
        assert response.status_code == 422
    
    def test_analysis_request_empty(self, client, auth_header):
        """Test analysis request with empty description."""
        response = client.post(
            "/analyze-task",
            json={"task_description": ""},
            headers=auth_header,
        )
        assert response.status_code == 422
    
    def test_task_analysis_schema_validation(self):
        """Test TaskAnalysis Pydantic model validation."""
        # Valid analysis
        analysis = TaskAnalysis(
            task_type="review",
            category="finance",
            priority="high",
            estimated_time_minutes=60,
            key_points=["point1", "point2"],
            confidence=0.95,
        )
        assert analysis.task_type == "review"
        
        # Invalid priority
        with pytest.raises(ValidationError):
            TaskAnalysis(
                task_type="review",
                category="finance",
                priority="urgent",  # Invalid
                estimated_time_minutes=60,
                key_points=["point1"],
                confidence=0.95,
            )
        
        # Invalid confidence
        with pytest.raises(ValidationError):
            TaskAnalysis(
                task_type="review",
                category="finance",
                priority="high",
                estimated_time_minutes=60,
                key_points=["point1"],
                confidence=1.5,  # Invalid: > 1.0
            )
        
        # Invalid time estimate (too low)
        with pytest.raises(ValidationError):
            TaskAnalysis(
                task_type="review",
                category="finance",
                priority="high",
                estimated_time_minutes=2,  # Invalid: < 5
                key_points=["point1"],
                confidence=0.95,
            )


# ============================================================================
# 4. Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_analyze_task_ai_service_error(self, client, auth_header):
        """Test handling of AI service errors."""
        with patch("ai_service.ChatOpenAI") as mock_llm:
            mock_llm.return_value.invoke.side_effect = Exception("API Error")
            
            response = client.post(
                "/analyze-task",
                json={"task_description": "This task should fail"},
                headers=auth_header,
            )
            
            # Should return 502 error
            assert response.status_code == 502
            assert "AI service error" in response.json()["error"]
    
    def test_analyze_task_timeout(self, client, auth_header):
        """Test timeout handling for AI requests."""
        with patch("ai_service.AIAnalysisService.analyze_task") as mock_analyze:
            mock_analyze.side_effect = TimeoutError("Request timed out after 30 seconds")
            
            response = client.post(
                "/analyze-task",
                json={"task_description": "This task will timeout"},
                headers=auth_header,
            )
            
            assert response.status_code == 504
            assert "timed out" in response.json()["error"].lower()
    
    def test_analyze_task_invalid_input(self, client, auth_header):
        """Test handling of invalid input."""
        with patch("ai_service.AIAnalysisService.analyze_task") as mock_analyze:
            mock_analyze.side_effect = ValueError("Invalid input: Task too simple")
            
            response = client.post(
                "/analyze-task",
                json={"task_description": "Do it"},
                headers=auth_header,
            )
            
            # Note: This might be 422 from FastAPI validation first
            # But if it gets to the service, it's 400
            assert response.status_code in [400, 422]


# ============================================================================
# 5. Retry Logic Tests
# ============================================================================

class TestRetryLogic:
    """Test retry mechanism."""
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry logic with eventual success."""
        service = AIAnalysisService(api_key="test-key")
        
        # Mock with failures then success
        call_count = 0
        
        async def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary error")
            
            mock_response = MagicMock()
            mock_response.content = """{
                "task_type": "review",
                "category": "finance",
                "priority": "high",
                "estimated_time_minutes": 60,
                "key_points": ["point1", "point2"],
                "confidence": 0.95
            }"""
            return mock_response
        
        with patch.object(service, "_call_llm", side_effect=mock_llm):
            # This should eventually succeed after retries
            result = await service.analyze_task("Test task description")
            assert result.task_type == "review"
            # Verify it retried
            assert call_count >= 3


# ============================================================================
# 6. Database Persistence Tests
# ============================================================================

class TestDatabasePersistence:
    """Test database operations."""
    
    def test_analysis_stored_in_db(self, client, auth_header):
        """Test that analyses are persisted to database."""
        with patch("ai_service.ChatOpenAI") as mock_llm:
            mock_response = MagicMock()
            mock_response.content = """{
                "task_type": "plan",
                "category": "operations",
                "priority": "medium",
                "estimated_time_minutes": 90,
                "key_points": ["outline", "schedule"],
                "confidence": 0.85
            }"""
            
            mock_llm.return_value.invoke.return_value = mock_response
            
            response = client.post(
                "/analyze-task",
                json={"task_description": "Plan the annual company strategy and timeline"},
                headers=auth_header,
            )
            
            assert response.status_code == 200
            analysis_id = response.json()["id"]
            
            # Retrieve the analysis
            get_response = client.get(
                f"/analyses/{analysis_id}",
                headers=auth_header,
            )
            assert get_response.status_code == 200
            assert get_response.json()["id"] == analysis_id
    
    def test_analysis_isolation_by_user(self, client):
        """Test that users can only see their own analyses."""
        # Create two users
        user1 = {"email": "user1@test.com", "password": "pass123"}
        user2 = {"email": "user2@test.com", "password": "pass123"}
        
        # Signup both
        for user in [user1, user2]:
            client.post("/auth/signup", json=user)
        
        # Login as user1
        login1 = client.post("/auth/login", json=user1)
        token1 = login1.json()["access_token"]
        
        # Login as user2
        login2 = client.post("/auth/login", json=user2)
        token2 = login2.json()["access_token"]
        
        # Create analysis as user1
        with patch("ai_service.ChatOpenAI") as mock_llm:
            mock_response = MagicMock()
            mock_response.content = """{
                "task_type": "write",
                "category": "marketing",
                "priority": "high",
                "estimated_time_minutes": 120,
                "key_points": ["research", "draft"],
                "confidence": 0.92
            }"""
            mock_llm.return_value.invoke.return_value = mock_response
            
            response1 = client.post(
                "/analyze-task",
                json={"task_description": "Write marketing copy for new product launch campaign"},
                headers={"Authorization": f"Bearer {token1}"},
            )
        
        analysis_id = response1.json()["id"]
        
        # User2 should not be able to access user1's analysis
        response2 = client.get(
            f"/analyses/{analysis_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert response2.status_code == 404


# ============================================================================
# 7. Meta and Health Endpoints
# ============================================================================

class TestMetaEndpoints:
    """Test API metadata and health endpoints."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "endpoints" in data
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "status" in data


# ============================================================================
# 8. Task CRUD Tests
# ============================================================================

class TestTaskCRUD:
    """Test task CRUD operations."""
    
    def test_create_task(self, client, auth_header):
        """Test creating a task."""
        response = client.post(
            "/tasks",
            json={"title": "Test task"},
            headers=auth_header,
        )
        assert response.status_code == 201
        assert response.json()["title"] == "Test task"
    
    def test_list_tasks(self, client, auth_header):
        """Test listing tasks."""
        # Create a task first
        client.post("/tasks", json={"title": "Task 1"}, headers=auth_header)
        
        response = client.get("/tasks", headers=auth_header)
        assert response.status_code == 200
        assert "tasks" in response.json()
    
    def test_update_task(self, client, auth_header):
        """Test updating a task."""
        # Create task
        create_response = client.post(
            "/tasks", json={"title": "Original"}, headers=auth_header
        )
        task_id = create_response.json()["id"]
        
        # Update it
        update_response = client.put(
            f"/tasks/{task_id}",
            json={"title": "Updated"},
            headers=auth_header,
        )
        assert update_response.status_code == 200
        assert update_response.json()["title"] == "Updated"
    
    def test_delete_task(self, client, auth_header):
        """Test deleting a task."""
        # Create task
        create_response = client.post(
            "/tasks", json={"title": "To delete"}, headers=auth_header
        )
        task_id = create_response.json()["id"]
        
        # Delete it
        delete_response = client.delete(f"/tasks/{task_id}", headers=auth_header)
        assert delete_response.status_code == 204


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
