import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://todo:todo@db:5432/tasks"
)


def _get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=psycopg.rows.dict_row)


def wait_for_db(timeout: int = 30, interval: float = 1.0) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            with _get_connection() as conn:
                conn.execute("SELECT 1")
            return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(interval)


class TaskRepository:
    def __init__(self) -> None:
        self._url = DATABASE_URL

    def init_db(self) -> None:
        wait_for_db()
        with _get_connection() as conn:
            # Users table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            # Refresh tokens table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            # Token blacklist (for logout)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    jti TEXT PRIMARY KEY,
                    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            # Jobs table for background task tracking
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    job_id UUID UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    input_data JSONB,
                    result_data JSONB,
                    error_message TEXT,
                    retries_remaining INTEGER DEFAULT 3,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ
                )
                """
            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_job_id ON jobs(job_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")

            conn.commit()

    # User operations
    def create_user(self, email: str, password_hash: str) -> Dict[str, Any]:
        with _get_connection() as conn:
            result = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email, created_at",
                (email, password_hash),
            )
            conn.commit()
            return result.fetchone()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            result = conn.execute(
                "SELECT id, email, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            return result.fetchone()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            result = conn.execute(
                "SELECT id, email, password_hash, created_at FROM users WHERE email = %s",
                (email,),
            )
            return result.fetchone()

    # Refresh token operations
    def store_refresh_token(self, user_id: int, token: str, expires_at: datetime) -> None:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO refresh_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (user_id, token, expires_at),
            )
            conn.commit()

    # Token blacklist operations
    def revoke_token(self, jti: str) -> None:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO token_blacklist (jti) VALUES (%s)",
                (jti,),
            )
            conn.commit()

    def is_token_revoked(self, jti: str) -> bool:
        with _get_connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM token_blacklist WHERE jti = %s",
                (jti,),
            )
            return result.fetchone() is not None

    # Job operations
    def create_job(
        self,
        user_id: int,
        job_id: UUID,
        job_type: str,
        input_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new background job."""
        with _get_connection() as conn:
            result = conn.execute(
                """
                INSERT INTO jobs (user_id, job_id, job_type, status, input_data)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, job_id, user_id, job_type, status, progress, created_at
                """,
                (user_id, str(job_id), job_type, "pending", 
                 psycopg.extras.Json(input_data) if input_data else None),
            )
            conn.commit()
            row = result.fetchone()
            return {
                **row,
                "job_id": UUID(str(row["job_id"])),
            }

    def get_job(self, job_id: UUID, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific job."""
        with _get_connection() as conn:
            result = conn.execute(
                """
                SELECT job_id, user_id, job_type, status, progress, 
                       input_data, result_data, error_message, retries_remaining,
                       created_at, started_at, completed_at
                FROM jobs WHERE job_id = %s AND user_id = %s
                """,
                (str(job_id), user_id),
            )
            row = result.fetchone()
            if row:
                return {
                    **row,
                    "job_id": UUID(str(row["job_id"])),
                }
            return None

    def list_jobs(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """List jobs for a user."""
        with _get_connection() as conn:
            result = conn.execute(
                """
                SELECT job_id, job_type, status, created_at, started_at, completed_at
                FROM jobs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s
                """,
                (user_id, limit),
            )
            return [
                {**row, "job_id": UUID(str(row["job_id"]))}
                for row in result.fetchall()
            ]

    def update_job_status(
        self,
        job_id: UUID,
        status: str,
        progress: int = None,
        result_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        retries_remaining: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update job status and metadata."""
        with _get_connection() as conn:
            updates = ["status = %s"]
            params = [status]

            if progress is not None:
                updates.append("progress = %s")
                params.append(progress)

            if result_data is not None:
                updates.append("result_data = %s")
                params.append(psycopg.extras.Json(result_data))

            if error_message is not None:
                updates.append("error_message = %s")
                params.append(error_message)

            if retries_remaining is not None:
                updates.append("retries_remaining = %s")
                params.append(retries_remaining)

            if status == "processing" and not any("started_at" in u for u in updates):
                updates.append("started_at = NOW()")

            if status == "success" or status == "failed":
                updates.append("completed_at = NOW()")

            params.append(str(job_id))

            query = f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = %s RETURNING *"
            result = conn.execute(query, params)
            conn.commit()

            row = result.fetchone()
            if row:
                return {
                    **row,
                    "job_id": UUID(str(row["job_id"])),
                }
            return None

    def get_job_by_celery_id(self, celery_task_id: str) -> Optional[Dict[str, Any]]:
        """Get job by Celery task ID (for worker lookups)."""
        with _get_connection() as conn:
            result = conn.execute(
                """
                SELECT job_id, user_id, job_type, status, progress, 
                       input_data, result_data, error_message, retries_remaining,
                       created_at, started_at, completed_at
                FROM jobs WHERE input_data->>'celery_task_id' = %s
                """,
                (celery_task_id,),
            )
            row = result.fetchone()
            if row:
                return {
                    **row,
                    "job_id": UUID(str(row["job_id"])),
                }
            return None
