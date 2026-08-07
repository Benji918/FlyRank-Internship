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


def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    done BOOLEAN NOT NULL DEFAULT FALSE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS revoked_tokens (
                    jti TEXT PRIMARY KEY,
                    revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            row = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
            if row["count"] == 0:
                conn.executemany(
                    "INSERT INTO tasks (title, done) VALUES (%s, %s)",
                    [("Buy milk", False), ("Write README", False), ("Push to GitHub", True)],
                )

    def create_user(self, email: str, password_hash: str) -> Dict[str, Any]:
        with _get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id, email, created_at",
                (email, password_hash),
            )
            return cursor.fetchone()

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            return conn.execute(
                "SELECT id, email, password_hash, created_at FROM users WHERE email = %s",
                (email,),
            ).fetchone()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            return conn.execute(
                "SELECT id, email, password_hash, created_at FROM users WHERE id = %s",
                (user_id,),
            ).fetchone()

    def revoke_jti(self, jti: str) -> None:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO revoked_tokens (jti) VALUES (%s) ON CONFLICT DO NOTHING",
                (jti,),
            )

    def is_token_revoked(self, jti: str) -> bool:
        with _get_connection() as conn:
            row = conn.execute(
                "SELECT jti FROM revoked_tokens WHERE jti = %s", (jti,)
            ).fetchone()
        return row is not None

    def store_refresh_token(self, user_id: int, refresh_token: str, expires_at: datetime) -> None:
        with _get_connection() as conn:
            conn.execute(
                "INSERT INTO refresh_tokens (token, user_id, expires_at) VALUES (%s, %s, %s)",
                (refresh_token, user_id, expires_at),
            )

    def delete_refresh_token(self, refresh_token: str) -> int:
        with _get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM refresh_tokens WHERE token = %s", (refresh_token,)
            )
            return cursor.rowcount

    def list_tasks(self, done: Optional[bool] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT id, title, done FROM tasks"
        clauses: List[str] = []
        params: List[Any] = []

        if done is not None:
            clauses.append("done = %s")
            params.append(done)

        if search:
            clauses.append("title ILIKE %s")
            params.append(f"%{search}%")

        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        query += " ORDER BY id"

        with _get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [_row_to_dict(row) for row in rows]

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        with _get_connection() as conn:
            return conn.execute(
                "SELECT id, title, done FROM tasks WHERE id = %s", (task_id,)
            ).fetchone()

    def create_task(self, title: str) -> Dict[str, Any]:
        with _get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING id, title, done",
                (title, False),
            )
            return cursor.fetchone()

    def update_task(
        self,
        task_id: int,
        title: Optional[str] = None,
        done: Optional[bool] = None,
    ) -> Dict[str, Any]:
        updates: List[str] = []
        params: List[Any] = []

        if title is not None:
            updates.append("title = %s")
            params.append(title)

        if done is not None:
            updates.append("done = %s")
            params.append(done)

        params.append(task_id)
        with _get_connection() as conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s", params
            )
            return conn.execute(
                "SELECT id, title, done FROM tasks WHERE id = %s", (task_id,)
            ).fetchone()

    def delete_task(self, task_id: int) -> int:
        with _get_connection() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
            return cursor.rowcount

    def get_stats(self) -> Dict[str, int]:
        with _get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, SUM(CASE WHEN done = TRUE THEN 1 ELSE 0 END) AS done_count FROM tasks"
            ).fetchone()

        total = row["total"] or 0
        done_count = row["done_count"] or 0
        return {"total": total, "done": done_count, "open": total - done_count}

    def reset_tasks(self) -> List[Dict[str, Any]]:
        with _get_connection() as conn:
            conn.execute("DELETE FROM tasks")
            conn.executemany(
                "INSERT INTO tasks (title, done) VALUES (%s, %s)",
                [("Buy milk", False), ("Write README", False), ("Push to GitHub", True)],
            )
            rows = conn.execute("SELECT id, title, done FROM tasks ORDER BY id").fetchall()
        return [_row_to_dict(row) for row in rows]
