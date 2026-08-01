# Task API

A small CRUD API for managing tasks with FastAPI and SQLite.

## Why SQLite?

SQLite is a lightweight embedded database that stores data on disk in a single file. It is a good fit for small projects, local development, and simple APIs because it requires no separate server process.

## Database file

The database lives in the project root as tasks.db. The application creates it automatically when it starts.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

The server starts at http://localhost:8000 and the API docs are available at http://localhost:8000/docs.

## What the app does

- Creates the tasks table if it does not exist
- Inserts three seed tasks only when the table is empty
- Persists task data across restarts
- Supports CRUD operations through the same API endpoints as before

## Example SQL query

```sql
SELECT * FROM tasks;
```

## Database viewer

A SQLite viewer such as DB Browser for SQLite can open tasks.db and show the table contents.

![SQLite database viewer placeholder](docs/database-viewer.png)

## Project structure

```text
todo-api/
├── main.py
├── tasks.db
├── requirements.txt
├── README.md
└── docs/
```
