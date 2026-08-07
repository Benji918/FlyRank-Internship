"""
Task API — Postgres-backed CRUD API with JWT auth.
"""
from typing import Any, Dict, Optional

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

repo = TaskRepository()

app = FastAPI(
    title="Task API",
    version="1.0",
    description="A Postgres-backed CRUD API with JWT auth, protected routes, and persistence.",
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
    return {
        "name": "Task API",
        "version": "1.0",
        "endpoints": ["/auth/signup", "/auth/login", "/public/info", "/protected/profile", "/tasks"],
    }


@app.get("/health", summary="Health check", tags=["meta"])
def health_check():
    task = repo.list_tasks()
    return {"status": "query successful", "query": task[0]["id"] if task else None}


@app.post("/auth/signup", status_code=201, tags=["auth"])
def signup(payload: AuthPayload):
    existing = repo.get_user_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    password_hash = hash_password(payload.password)
    user = repo.create_user(payload.email, password_hash)
    return {"id": user["id"], "email": user["email"], "created_at": user["created_at"]}


@app.post("/auth/login", response_model=AuthResponse, tags=["auth"])
def login(payload: AuthPayload):
    user = repo.get_user_by_email(payload.email)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid login credentials")

    access_token = create_access_token(user_id=user["id"], email=user["email"])
    refresh_token = create_refresh_token(user_id=user["id"])
    return AuthResponse(access_token=access_token, refresh_token=refresh_token)


@app.post("/auth/logout", status_code=204, tags=["auth"])
def logout(current=Depends(get_current_user)):
    repo.revoke_jti(current["payload"]["jti"])
    return None


@app.get("/public/info", summary="Public info", tags=["public"])
def public_info():
    return {"message": "Welcome stranger! This info is public."}


@app.get("/protected/profile", summary="Private profile", tags=["protected"], response_model=Dict[str, Any])
def protected_profile(current=Depends(get_current_user)):
    user = current["user"]
    return {
        "id": user["id"],
        "email": user["email"],
        "created_at": user["created_at"],
    }


@app.get("/protected/dashboard", summary="Private dashboard", tags=["protected"])
def protected_dashboard(current=Depends(get_current_user)):
    return {
        "message": f"Welcome back, {current['user']['email']}",
        "protected": True,
    }


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
