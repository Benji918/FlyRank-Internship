import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

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

            # Tasks table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL,
                    done BOOLEAN DEFAULT FALSE,
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

            # AI Analyses table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    task_description TEXT NOT NULL,
                    task_type TEXT,
                    category TEXT,
                    priority TEXT,
                    estimated_time_minutes INTEGER,
                    key_points TEXT[],
                    confidence FLOAT,
                    error TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

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

    def get_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            result = conn.execute(
                "SELECT user_id, expires_at FROM refresh_tokens WHERE token = %s",
                (token,),
            )
            return result.fetchone()

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

    # Task operations
    def create_task(self, user_id: int, title: str) -> Dict[str, Any]:
        with _get_connection() as conn:
            result = conn.execute(
                "INSERT INTO tasks (user_id, title) VALUES (%s, %s) RETURNING id, title, done, created_at",
                (user_id, title),
            )
            conn.commit()
            return result.fetchone()

    def list_tasks(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        with _get_connection() as conn:
            if user_id:
                result = conn.execute(
                    "SELECT id, title, done FROM tasks WHERE user_id = %s ORDER BY id DESC",
                    (user_id,),
                )
            else:
                result = conn.execute(
                    "SELECT id, title, done FROM tasks ORDER BY id DESC LIMIT 10"
                )
            return result.fetchall()

    def get_task(self, task_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            if user_id:
                result = conn.execute(
                    "SELECT id, title, done FROM tasks WHERE id = %s AND user_id = %s",
                    (task_id, user_id),
                )
            else:
                result = conn.execute(
                    "SELECT id, title, done FROM tasks WHERE id = %s",
                    (task_id,),
                )
            return result.fetchone()

    def update_task(self, task_id: int, user_id: int, title: Optional[str] = None, done: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            updates = []
            params = []
            if title is not None:
                updates.append("title = %s")
                params.append(title)
            if done is not None:
                updates.append("done = %s")
                params.append(done)

            if not updates:
                return self.get_task(task_id, user_id)

            params.extend([task_id, user_id])
            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s AND user_id = %s RETURNING id, title, done"
            result = conn.execute(query, params)
            conn.commit()
            return result.fetchone()

    def delete_task(self, task_id: int, user_id: int) -> bool:
        with _get_connection() as conn:
            result = conn.execute(
                "DELETE FROM tasks WHERE id = %s AND user_id = %s",
                (task_id, user_id),
            )
            conn.commit()
            return result.rowcount > 0

    # Analysis operations
    def store_analysis(
        self,
        user_id: int,
        task_description: str,
        task_type: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        estimated_time_minutes: Optional[int] = None,
        key_points: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        with _get_connection() as conn:
            result = conn.execute(
                """
                INSERT INTO analyses 
                (user_id, task_description, task_type, category, priority, 
                 estimated_time_minutes, key_points, confidence, error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, task_type, category, priority, estimated_time_minutes, key_points, confidence, created_at
                """,
                (
                    user_id,
                    task_description,
                    task_type,
                    category,
                    priority,
                    estimated_time_minutes,
                    key_points,
                    confidence,
                    error,
                ),
            )
            conn.commit()
            return result.fetchone()

    def get_analysis(self, analysis_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, task_description, task_type, category, priority, 
                       estimated_time_minutes, key_points, confidence, error, created_at
                FROM analyses WHERE id = %s AND user_id = %s
                """,
                (analysis_id, user_id),
            )
            return result.fetchone()

    def list_analyses(self, user_id: int) -> List[Dict[str, Any]]:
        with _get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, task_description, task_type, category, priority, 
                       estimated_time_minutes, key_points, confidence, created_at
                FROM analyses WHERE user_id = %s ORDER BY created_at DESC LIMIT 20
                """,
                (user_id,),
            )
            return result.fetchall()
