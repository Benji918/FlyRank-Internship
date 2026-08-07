"""
Task API — Postgres-backed CRUD API.
"""
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from repository import TaskRepository

repo = TaskRepository()

app = FastAPI(
    title="Task API",
    version="1.0",
    description="A tiny Postgres-backed CRUD API for managing a to-do list.",
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
    task = repo.list_tasks()
    return {"status": "query successful", "query": task[0]["id"] if task else None}


@app.get("/tasks", summary="List tasks", tags=["tasks"])
def list_tasks(done: Optional[bool] = None, search: Optional[str] = None):
    return repo.list_tasks(done=done, search=search)


@app.get("/tasks/{task_id}", summary="Get one task", tags=["tasks"])
def get_task(task_id: int):
    task = repo.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.post("/tasks", status_code=201, summary="Create a task", tags=["tasks"])
def create_task(payload: TaskCreate):
    if not payload.title or not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' is required and cannot be empty")

    return repo.create_task(payload.title.strip())


@app.put("/tasks/{task_id}", summary="Update a task", tags=["tasks"])
def update_task(task_id: int, payload: TaskUpdate):
    existing = repo.get_task(task_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    if payload.title is None and payload.done is None:
        raise HTTPException(status_code=400, detail="Provide at least 'title' or 'done' to update")

    if payload.title is not None and not payload.title.strip():
        raise HTTPException(status_code=400, detail="Field 'title' cannot be empty")

    task = repo.update_task(
        task_id,
        title=payload.title.strip() if payload.title is not None else None,
        done=payload.done,
    )
    return task


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task", tags=["tasks"])
def delete_task(task_id: int):
    deleted = repo.delete_task(task_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return None


@app.get("/stats", summary="Task counts", tags=["extras"])
def get_stats():
    return repo.get_stats()


@app.post("/reset", summary="Restore the 3 example tasks", tags=["extras"])
def reset_tasks():
    tasks = repo.reset_tasks()
    return {"status": "reset", "tasks": tasks}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="info", reload=True)
