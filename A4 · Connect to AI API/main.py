"""
Task API with AI Analysis — Postgres-backed CRUD API with JWT auth and LLM integration.
"""
from typing import Any, Dict, Optional
from datetime import datetime

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import (
    AuthPayload,
    AuthResponse,
    create_access_token,
    create_refresh_token,
    get_current_user,
    hash_password,
    verify_password,
)
from repository import TaskRepository
from ai_service import get_ai_service, TaskAnalysis

repo = TaskRepository()

app = FastAPI(
    title="Task API with AI Analysis",
    version="2.0",
    description="A Postgres-backed CRUD API with JWT auth, protected routes, AI analysis, and persistence.",
)


@app.on_event("startup")
async def startup_event():
    repo.init_db()


@app.exception_handler(HTTPException)
async def http_exception_as_error_key(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_as_400(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0]
    field = first_error["loc"][-1] if first_error["loc"] else "body"
    return JSONResponse(
        status_code=400,
        content={"error": f"Invalid value for '{field}': {first_error['msg']}"},
    )


# ============================================================================
# Pydantic Models
# ============================================================================

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, description="What needs doing")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    done: Optional[bool] = None


class AnalysisRequest(BaseModel):
    task_description: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="Task description to analyze"
    )


class AnalysisResponse(BaseModel):
    id: int
    analysis: TaskAnalysis
    created_at: datetime


# ============================================================================
# Meta Endpoints
# ============================================================================

@app.get("/", summary="API description", tags=["meta"])
def read_root():
    return {
        "name": "Task API with AI Analysis",
        "version": "2.0",
        "endpoints": [
            "/auth/signup",
            "/auth/login",
            "/auth/logout",
            "/public/info",
            "/protected/profile",
            "/tasks",
            "/analyze-task",
        ],
    }


@app.get("/health", summary="Health check", tags=["meta"])
def health_check():
    try:
        tasks = repo.list_tasks()
        ai_service = get_ai_service()
        return {
            "status": "healthy",
            "database": "connected",
            "ai_service": ai_service.health_check(),
            "recent_tasks": len(tasks),
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.post("/auth/signup", status_code=201, tags=["auth"])
def signup(payload: AuthPayload):
    """Create a new user account."""
    existing = repo.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = hash_password(payload.password)
    user = repo.create_user(payload.email, password_hash)
    return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}


@app.post("/auth/login", response_model=AuthResponse, tags=["auth"])
def login(payload: AuthPayload):
    """Login with email and password."""
    user = repo.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid login credentials")

    access_token = create_access_token(user_id=user["id"], email=user["email"])
    refresh_token = create_refresh_token(user_id=user["id"])
    return AuthResponse(access_token=access_token, refresh_token=refresh_token)


@app.post("/auth/logout", status_code=204, tags=["auth"])
def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Logout and invalidate token."""
    jti = current_user["payload"].get("jti")
    if jti:
        repo.revoke_token(jti)
    return


# ============================================================================
# Public Endpoints
# ============================================================================

@app.get("/public/info", tags=["public"])
def public_info():
    return {"message": "This is public information"}


# ============================================================================
# Protected Endpoints
# ============================================================================

@app.get("/protected/profile", tags=["protected"])
def get_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user profile."""
    user = current_user["user"]
    return {
        "id": user["id"],
        "email": user["email"],
        "created_at": user["created_at"],
    }


# ============================================================================
# Task CRUD Endpoints
# ============================================================================

@app.post("/tasks", status_code=201, tags=["tasks"])
def create_task(
    payload: TaskCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new task for the authenticated user."""
    user_id = current_user["user"]["id"]
    task = repo.create_task(user_id, payload.title)
    return task


@app.get("/tasks", tags=["tasks"])
def list_tasks(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all tasks for the authenticated user."""
    user_id = current_user["user"]["id"]
    tasks = repo.list_tasks(user_id)
    return {"tasks": tasks}


@app.get("/tasks/{task_id}", tags=["tasks"])
def get_task(
    task_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific task."""
    user_id = current_user["user"]["id"]
    task = repo.get_task(task_id, user_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.put("/tasks/{task_id}", tags=["tasks"])
def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a task."""
    user_id = current_user["user"]["id"]
    task = repo.update_task(task_id, user_id, payload.title, payload.done)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.delete("/tasks/{task_id}", status_code=204, tags=["tasks"])
def delete_task(
    task_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a task."""
    user_id = current_user["user"]["id"]
    success = repo.delete_task(task_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return


# ============================================================================
# AI Analysis Endpoint
# ============================================================================

@app.post("/analyze-task", response_model=AnalysisResponse, tags=["ai"])
async def analyze_task(
    payload: AnalysisRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Analyze a task description using AI.
    
    This endpoint:
    - Takes a task description (10-5000 chars)
    - Uses OpenAI's GPT to analyze it
    - Returns structured analysis with category, priority, time estimate, etc.
    - Stores the analysis in the database
    - Implements 30-second timeout and retry logic
    - Validates all responses against schema
    """
    user_id = current_user["user"]["id"]
    
    try:
        ai_service = get_ai_service()
        
        # Call AI service with timeout and retry logic
        analysis = await ai_service.analyze_task(payload.task_description)
        
        # Store in database
        result = repo.store_analysis(
            user_id=user_id,
            task_description=payload.task_description,
            task_type=analysis.task_type,
            category=analysis.category,
            priority=analysis.priority,
            estimated_time_minutes=analysis.estimated_time_minutes,
            key_points=analysis.key_points,
            confidence=analysis.confidence,
        )
        
        return AnalysisResponse(
            id=result["id"],
            analysis=TaskAnalysis(
                task_type=result["task_type"],
                category=result["category"],
                priority=result["priority"],
                estimated_time_minutes=result["estimated_time_minutes"],
                key_points=result["key_points"],
                confidence=result["confidence"],
            ),
            created_at=result["created_at"],
        )
    
    except ValueError as e:
        # Input validation error
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    
    except TimeoutError as e:
        # AI service timeout
        repo.store_analysis(
            user_id=user_id,
            task_description=payload.task_description,
            error="Analysis timeout - AI service did not respond in time",
        )
        raise HTTPException(status_code=504, detail=str(e))
    
    except Exception as e:
        # Other AI service errors
        error_msg = str(e)
        repo.store_analysis(
            user_id=user_id,
            task_description=payload.task_description,
            error=error_msg,
        )
        raise HTTPException(
            status_code=502,
            detail=f"AI service error: {error_msg[:100]}"
        )


@app.get("/analyses", tags=["ai"])
def list_analyses(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all analyses for the authenticated user."""
    user_id = current_user["user"]["id"]
    analyses = repo.list_analyses(user_id)
    return {"analyses": analyses}


@app.get("/analyses/{analysis_id}", tags=["ai"])
def get_analysis(
    analysis_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific analysis."""
    user_id = current_user["user"]["id"]
    analysis = repo.get_analysis(analysis_id, user_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
