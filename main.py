"""
Task API — a small in-memory CRUD API built with FastAPI.

FlyRank Internship · Backend Track · W2 · A1 — Build your first CRUD API

Data lives only in memory (a Python list). Restarting the server resets it
to the three seed tasks below — that's expected, not a bug (see README).
"""
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI(
    title="Task API",
    version="1.0",
    description="A tiny in-memory CRUD API for managing a to-do list.",
)


@app.exception_handler(HTTPException)
async def http_exception_as_error_key(request: Request, exc: HTTPException):
    """Normalize every raised HTTPException to the spec's {"error": "..."} shape."""
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_error_as_400(request: Request, exc: RequestValidationError):
    """
    The assignment's spec says a bad POST/PUT body is a 400, not FastAPI's
    default 422. We keep Pydantic's validation (it's doing real work) but
    translate its error response to the status code the spec asks for.
    """
    first_error = exc.errors()[0]
    field = first_error["loc"][-1] if first_error["loc"] else "body"
    return JSONResponse(
        status_code=400,
        content={"error": f"Invalid value for '{field}': {first_error['msg']}"},
    )

# ---------------------------------------------------------------------------
# Stage 2 — in-memory "database": a plain list, seeded with 3 example tasks
# ---------------------------------------------------------------------------

tasks = [
    {"id": 1, "title": "Buy milk", "done": False},
    {"id": 2, "title": "Write README", "done": False},
    {"id": 3, "title": "Push to GitHub", "done": True},
]

_next_id = 4  # simple auto-increment counter for new tasks


def _find_task(task_id: int):
    for task in tasks:
        if task["id"] == task_id:
            return task
    return None


# ---------------------------------------------------------------------------
# Request/response models (Pydantic) — used for validation (Stage 3 & 4)
# ---------------------------------------------------------------------------

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, description="What needs doing")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    done: Optional[bool] = None


# ---------------------------------------------------------------------------
# Stage 1 — root and health endpoints
# ---------------------------------------------------------------------------

@app.get("/", summary="API description", tags=["meta"])
def read_root():
    """Front door: tells a visitor what this API is and where to look next."""
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", summary="Health check", tags=["meta"])
def health_check():
    """Used by uptime monitors / load balancers to check the server is alive."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Stage 2 — Read
# ---------------------------------------------------------------------------

@app.get("/tasks", summary="List tasks (optionally filter/search)", tags=["tasks"])
def list_tasks(done: Optional[bool] = None, search: Optional[str] = None):
    """
    List all tasks.

    Extras (optional query parameters):
    - `done`: filter to only finished (`true`) or only open (`false`) tasks.
    - `search`: only tasks whose title contains this text (case-insensitive).
    """
    result = tasks

    if done is not None:
        result = [t for t in result if t["done"] == done]

    if search:
        needle = search.lower()
        result = [t for t in result if needle in t["title"].lower()]

    return result


@app.get("/tasks/{task_id}", summary="Get one task", tags=["tasks"])
def get_task(task_id: int):
    """Return a single task by id, or 404 if it doesn't exist."""
    task = _find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


# ---------------------------------------------------------------------------
# Stage 3 — Create
# ---------------------------------------------------------------------------

@app.post("/tasks", status_code=201, summary="Create a task", tags=["tasks"])
def create_task(payload: TaskCreate):
    """
    Create a new task from `{"title": "..."}`.

    Pydantic validation already rejects a missing/empty title with a 422 by
    default; we additionally guard here so the assignment's required 400
    (not 422) is what the client actually receives.
    """
    global _next_id

    if not payload.title or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and cannot be empty")

    new_task = {"id": _next_id, "title": payload.title.strip(), "done": False}
    tasks.append(new_task)
    _next_id += 1
    return new_task


# ---------------------------------------------------------------------------
# Stage 4 — Update & Delete
# ---------------------------------------------------------------------------

@app.put("/tasks/{task_id}", summary="Replace a task's title/done", tags=["tasks"])
def update_task(task_id: int, payload: TaskUpdate):
    """Update a task's title and/or done flag. 404 if unknown, 400 if the body is invalid."""
    task = _find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if payload.title is None and payload.done is None:
        raise HTTPException(status_code=400, detail="Provide at least 'title' or 'done' to update")

    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(status_code=400, detail="Field 'title' cannot be empty")
        task["title"] = payload.title.strip()

    if payload.done is not None:
        task["done"] = payload.done

    return task


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task", tags=["tasks"])
def delete_task(task_id: int):
    """Remove a task. 404 if unknown, otherwise 204 with an empty body."""
    task = _find_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    tasks.remove(task)
    return None


# ---------------------------------------------------------------------------
# Extras (optional, all built): stats + seed/reset
# ---------------------------------------------------------------------------

@app.get("/stats", summary="Task counts", tags=["extras"])
def get_stats():
    """First taste of the server computing something instead of just storing it."""
    total = len(tasks)
    done_count = sum(1 for t in tasks if t["done"])
    return {"total": total, "done": done_count, "open": total - done_count}


@app.post("/reset", summary="Restore the 3 example tasks", tags=["extras"])
def reset_tasks():
    """Wipes whatever is in memory and restores the original 3 seed tasks. Handy for demos."""
    global tasks, _next_id
    tasks = [
        {"id": 1, "title": "Buy milk", "done": False},
        {"id": 2, "title": "Write README", "done": False},
        {"id": 3, "title": "Push to GitHub", "done": True},
    ]
    _next_id = 4
    return {"status": "reset", "tasks": tasks}


if __name__ == "__main__":

    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info", reload=True)