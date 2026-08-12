"""
Task API with Background Jobs — FastAPI with Celery for async processing.

Endpoints return 202 Accepted immediately, jobs process in background.
"""
import logging
from typing import Any, Dict, Optional
from datetime import datetime
from uuid import uuid4, UUID

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
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
from celery_app import analyze_pdf_task, analyze_text_task

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

repo = TaskRepository()

app = FastAPI(
    title="Task API with Background Jobs",
    version="3.0",
    description="FastAPI with Celery for async background job processing and monitoring.",
)


@app.on_event("startup")
async def startup_event():
    repo.init_db()
    logger.info("Database initialized")


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

class JobSubmissionResponse(BaseModel):
    """Response when job is submitted (202 Accepted)."""
    job_id: UUID = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Initial status (always 'pending')")
    message: str = Field(..., description="User-friendly message")


class JobStatusResponse(BaseModel):
    """Response for job status check."""
    job_id: UUID
    status: str  # pending, processing, success, failed
    progress: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retries_remaining: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobListResponse(BaseModel):
    """Response for job list."""
    jobs: list[Dict[str, Any]]


class AnalyzeTextRequest(BaseModel):
    """Request for text analysis."""
    text: str = Field(..., min_length=10, max_length=10000, description="Text to analyze")


# ============================================================================
# Meta Endpoints
# ============================================================================

@app.get("/", summary="API description", tags=["meta"])
def read_root():
    return {
        "name": "Task API with Background Jobs",
        "version": "3.0",
        "pattern": "202 Accept → Background Processing → Status Check",
        "endpoints": [
            "/auth/signup",
            "/auth/login",
            "/auth/logout",
            "/analyze-pdf",
            "/analyze-text",
            "/jobs/{job_id}",
            "/jobs",
        ],
    }


@app.get("/health", summary="Health check", tags=["meta"])
def health_check():
    try:
        # Check database
        from repository import TaskRepository
        repo = TaskRepository()
        
        # Check Celery
        from celery_app import celery_app
        celery_status = celery_app.control.inspect().active()
        
        return {
            "status": "healthy",
            "database": "connected",
            "celery_workers": len(celery_status) if celery_status else 0,
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
# Job Submission Endpoints (Return 202 Accepted)
# ============================================================================

@app.post("/analyze-pdf", status_code=202, response_model=JobSubmissionResponse, tags=["jobs"])
async def submit_pdf_analysis(
    file: UploadFile = File(..., description="PDF file to analyze"),
    analysis_type: str = "summary",
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Submit a PDF for background analysis.
    
    Returns 202 Accepted immediately with job ID.
    Use /jobs/{job_id} to check status.
    
    Args:
        file: PDF file (max 10MB recommended)
        analysis_type: 'summary', 'detailed', or 'keywords'
    
    Returns:
        202 with job_id for status tracking
    """
    user_id = current_user["user"]["id"]
    job_id = uuid4()
    
    # Validate file
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        # Save file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        # Create job record
        repo.create_job(
            user_id=user_id,
            job_id=job_id,
            job_type="pdf_analysis",
            input_data={
                "file_path": tmp_path,
                "analysis_type": analysis_type,
                "file_name": file.filename,
            },
        )
        
        # Queue Celery task (fire and forget, will update DB status)
        task = analyze_pdf_task.delay(
            job_id=str(job_id),
            user_id=user_id,
            file_path=tmp_path,
            analysis_type=analysis_type,
        )
        
        logger.info(f"Submitted PDF analysis job {job_id} for user {user_id}")
        
        return JobSubmissionResponse(
            job_id=job_id,
            status="pending",
            message="PDF analysis started. Check status endpoint for updates.",
        )
    
    except Exception as e:
        logger.exception(f"Error submitting PDF analysis: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to submit job: {str(e)}")


@app.post("/analyze-text", status_code=202, response_model=JobSubmissionResponse, tags=["jobs"])
async def submit_text_analysis(
    payload: AnalyzeTextRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Submit text for background analysis.
    
    Returns 202 Accepted immediately with job ID.
    """
    user_id = current_user["user"]["id"]
    job_id = uuid4()
    
    try:
        # Create job record
        repo.create_job(
            user_id=user_id,
            job_id=job_id,
            job_type="text_analysis",
            input_data={"text": payload.text},
        )
        
        # Queue task
        task = analyze_text_task.delay(
            job_id=str(job_id),
            user_id=user_id,
            text_content=payload.text,
        )
        
        logger.info(f"Submitted text analysis job {job_id} for user {user_id}")
        
        return JobSubmissionResponse(
            job_id=job_id,
            status="pending",
            message="Text analysis started. Check status endpoint for updates.",
        )
    
    except Exception as e:
        logger.exception(f"Error submitting text analysis: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to submit job: {str(e)}")


# ============================================================================
# Job Status Endpoints
# ============================================================================

@app.get("/jobs/{job_id}", response_model=JobStatusResponse, tags=["jobs"])
def get_job_status(
    job_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Get the status of a submitted job.
    
    Returns current status, progress, and results (if available).
    """
    user_id = current_user["user"]["id"]
    
    job = repo.get_job(job_id, user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress=job["progress"],
        result=job["result_data"],
        error=job["error_message"],
        retries_remaining=job["retries_remaining"],
        created_at=job["created_at"],
        started_at=job["started_at"],
        completed_at=job["completed_at"],
    )


@app.get("/jobs", response_model=JobListResponse, tags=["jobs"])
def list_user_jobs(
    current_user: Dict[str, Any] = Depends(get_current_user),
    limit: int = 50,
):
    """
    List all jobs for the authenticated user.
    
    Returns list of job summaries with latest jobs first.
    """
    user_id = current_user["user"]["id"]
    jobs = repo.list_jobs(user_id, limit=limit)
    
    return JobListResponse(jobs=jobs)


# ============================================================================
# Protected Profile Endpoint
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
