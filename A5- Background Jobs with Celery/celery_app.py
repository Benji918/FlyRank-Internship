"""
Celery configuration and task definitions for background job processing.
"""
import os
import json
import logging
from typing import Optional, Dict, Any
from uuid import UUID

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Celery configuration
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task configuration
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minute hard limit
    task_soft_time_limit=28 * 60,  # 28 minute soft limit (allows cleanup)
    # Retry configuration
    task_acks_late=True,  # Acknowledge task after completion
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks (prevent memory leaks)
    # Result backend configuration
    result_expires=86400,  # Keep results for 24 hours
    result_extended=True,  # Store result in metadata
)

logger = logging.getLogger(__name__)


# ============================================================================
# PDF Analysis Task
# ============================================================================

@celery_app.task(
    bind=True,
    name="tasks.analyze_pdf",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,  # Max 10 minute backoff
    retry_jitter=True,
)
def analyze_pdf_task(
    self,
    job_id: str,
    user_id: int,
    file_path: str,
    analysis_type: str = "summary",
) -> Dict[str, Any]:
    """
    Analyze a PDF document using AI.
    
    Args:
        job_id: Unique job identifier
        user_id: User ID who submitted the job
        file_path: Path to the PDF file
        analysis_type: Type of analysis ('summary', 'detailed', 'keywords')
    
    Returns:
        Dictionary with analysis results
    
    Raises:
        Exception: On any error (will trigger retry logic)
    """
    from repository import TaskRepository
    from ai_service import analyze_pdf_content
    
    repo = TaskRepository()
    job_uuid = UUID(job_id)
    
    try:
        # Update job status to processing
        repo.update_job_status(job_uuid, "processing", progress=10)
        logger.info(f"Starting PDF analysis for job {job_id}")
        
        # Extract text from PDF
        logger.debug(f"Extracting text from {file_path}")
        repo.update_job_status(job_uuid, "processing", progress=20)
        
        from ai_service import extract_pdf_text
        text_content = extract_pdf_text(file_path)
        
        if not text_content:
            raise ValueError("PDF is empty or unreadable")
        
        repo.update_job_status(job_uuid, "processing", progress=40)
        
        # Analyze with AI
        logger.debug(f"Analyzing content with AI (type: {analysis_type})")
        result = analyze_pdf_content(text_content, analysis_type)
        
        repo.update_job_status(job_uuid, "processing", progress=80)
        
        # Store results
        final_result = {
            "analysis_type": analysis_type,
            "summary": result.get("summary"),
            "key_points": result.get("key_points", []),
            "pages_analyzed": result.get("pages_analyzed", 0),
            "confidence": result.get("confidence", 0.0),
            "full_analysis": result.get("full_analysis"),
        }
        
        repo.update_job_status(
            job_uuid,
            "success",
            progress=100,
            result_data=final_result,
        )
        
        logger.info(f"Successfully completed PDF analysis for job {job_id}")
        return {
            "status": "success",
            "result": final_result,
        }
    
    except Exception as exc:
        logger.exception(f"Error in PDF analysis task {job_id}: {exc}")
        
        # Update retries remaining
        retries_left = self.max_retries - self.request.retries
        
        if retries_left > 0:
            # Will retry
            error_msg = f"{str(exc)} (Retry {self.request.retries + 1}/{self.max_retries})"
            repo.update_job_status(
                job_uuid,
                "processing",
                progress=0,
                error_message=error_msg,
                retries_remaining=retries_left,
            )
            # Raise to trigger retry
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        else:
            # Out of retries - mark as failed
            repo.update_job_status(
                job_uuid,
                "failed",
                error_message=str(exc),
                retries_remaining=0,
            )
            logger.error(f"PDF analysis task {job_id} exhausted all retries")
            return {
                "status": "failed",
                "error": str(exc),
                "retries_remaining": 0,
            }


# ============================================================================
# Text Analysis Task (Simple version for testing)
# ============================================================================

@celery_app.task(
    bind=True,
    name="tasks.analyze_text",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def analyze_text_task(
    self,
    job_id: str,
    user_id: int,
    text_content: str,
) -> Dict[str, Any]:
    """
    Analyze text content using AI.
    
    This is a simpler version for testing without PDF parsing.
    """
    from repository import TaskRepository
    from ai_service import analyze_text_content
    
    repo = TaskRepository()
    job_uuid = UUID(job_id)
    
    try:
        repo.update_job_status(job_uuid, "processing", progress=30)
        
        result = analyze_text_content(text_content)
        
        repo.update_job_status(
            job_uuid,
            "success",
            progress=100,
            result_data=result,
        )
        
        return {
            "status": "success",
            "result": result,
        }
    
    except Exception as exc:
        logger.exception(f"Error in text analysis task {job_id}: {exc}")
        
        retries_left = self.max_retries - self.request.retries
        
        if retries_left > 0:
            error_msg = f"{str(exc)} (Retry {self.request.retries + 1}/{self.max_retries})"
            repo.update_job_status(
                job_uuid,
                "processing",
                progress=0,
                error_message=error_msg,
                retries_remaining=retries_left,
            )
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        else:
            repo.update_job_status(
                job_uuid,
                "failed",
                error_message=str(exc),
                retries_remaining=0,
            )
            return {
                "status": "failed",
                "error": str(exc),
            }


# ============================================================================
# Task Monitoring and Alerts
# ============================================================================

@celery_app.task(name="tasks.check_stuck_jobs")
def check_stuck_jobs():
    """
    Periodic task to check for stuck jobs and alert.
    Should be scheduled via beat scheduler.
    """
    from datetime import datetime, timedelta
    from repository import TaskRepository
    
    repo = TaskRepository()
    
    # Find jobs stuck in processing for > 10 minutes
    try:
        # This would need a SQL query to find old processing jobs
        logger.warning("Checking for stuck jobs...")
        # Implementation would query jobs with old started_at timestamps
    except Exception as exc:
        logger.error(f"Error checking stuck jobs: {exc}")


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """Set up periodic tasks (optional)."""
    # sender.add_periodic_task(
    #     300.0,  # Every 5 minutes
    #     check_stuck_jobs.s(),
    #     name="Check for stuck jobs",
    # )
    pass
