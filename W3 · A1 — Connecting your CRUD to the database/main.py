"""
Task API — SQLite-backed CRUD API.
"""
import os
import sqlite3
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DB_PATH = os.environ.get("TASKS_DB_PATH", os.path.join(os.path.dirname(__file__), "tasks.db"))


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def init_db() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done BOOLEAN NOT NULL DEFAULT 0
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
        if row["count"] == 0:
            conn.executemany(
                "INSERT INTO tasks (title, done) VALUES (?, ?)",
                [("Buy milk", 0), ("Write README", 0), ("Push to GitHub", 1)],
            )


init_db()

app = FastAPI(
    title="Task API",
    version="1.0",
    description="A tiny SQLite-backed CRUD API for managing a to-do list.",
)


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


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, description="What needs doing")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    done: Optional[bool] = None


@app.get("/", summary="API description", tags=["meta"])
def read_root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", summary="Health check", tags=["meta"])
def health_check():
    query = "SELECT * FROM tasks"
    with _get_connection() as conn:
        result = conn.execute(query).fetchone()
    return {"status": "query successful", "query": result[0] if result else None}


@app.get("/tasks", summary="List tasks", tags=["tasks"])
def list_tasks(done: Optional[bool] = None, search: Optional[str] = None):
    query = "SELECT id, title, done FROM tasks"
    clauses = []
    params = []

    if done is not None:
        clauses.append("done = ?")
        params.append(1 if done else 0)

    if search:
        clauses.append("title LIKE ?")
        params.append(f"%{search}%")

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY id"

    with _get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [_row_to_dict(row) for row in rows]


@app.get("/tasks/{task_id}", summary="Get one task", tags=["tasks"])
def get_task(task_id: int):
    with _get_connection() as conn:
        row = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return _row_to_dict(row)


@app.post("/tasks", status_code=201, summary="Create a task", tags=["tasks"])
def create_task(payload: TaskCreate):
    if not payload.title or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and cannot be empty")

    title = payload.title.strip()
    with _get_connection() as conn:
        cursor = conn.execute("INSERT INTO tasks (title, done) VALUES (?, ?)", (title, 0))
        task_id = cursor.lastrowid
        row = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)).fetchone()

    return _row_to_dict(row)


@app.put("/tasks/{task_id}", summary="Update a task", tags=["tasks"])
def update_task(task_id: int, payload: TaskUpdate):
    with _get_connection() as conn:
        existing = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if payload.title is None and payload.done is None:
            raise HTTPException(status_code=400, detail="Provide at least 'title' or 'done' to update")

        updates = []
        params = []

        if payload.title is not None:
            if not payload.title.strip():
                raise HTTPException(status_code=400, detail="Field 'title' cannot be empty")
            updates.append("title = ?")
            params.append(payload.title.strip())

        if payload.done is not None:
            updates.append("done = ?")
            params.append(1 if payload.done else 0)

        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute("SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)).fetchone()

    return _row_to_dict(row)


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task", tags=["tasks"])
def delete_task(task_id: int):
    with _get_connection() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return None


@app.get("/stats", summary="Task counts", tags=["extras"])
def get_stats():
    with _get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN done = 1 THEN 1 ELSE 0 END) AS done_count FROM tasks"
        ).fetchone()

    total = row["total"] or 0
    done_count = row["done_count"] or 0
    return {"total": total, "done": done_count, "open": total - done_count}


@app.post("/reset", summary="Restore the 3 example tasks", tags=["extras"])
def reset_tasks():
    with _get_connection() as conn:
        conn.execute("DELETE FROM tasks")
        conn.executemany(
            "INSERT INTO tasks (title, done) VALUES (?, ?)",
            [("Buy milk", 0), ("Write README", 0), ("Push to GitHub", 1)],
        )
        rows = conn.execute("SELECT id, title, done FROM tasks ORDER BY id").fetchall()

    return {"status": "reset", "tasks": [_row_to_dict(row) for row in rows]}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info", reload=True)
