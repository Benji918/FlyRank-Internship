# W3 · A1 — Connecting your CRUD to the database

This folder contains a duplicate of the task API that now stores data in SQLite instead of memory.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

The app creates a file named tasks.db automatically on first start and seeds the table only if it is empty.
