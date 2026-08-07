# A3 · Containerize your stack

This folder contains a Dockerized Task API using Postgres as the storage backend.

## What changed

- The app now uses Postgres instead of SQLite.
- Database configuration is loaded from `.env`.
- Docker Compose starts both the app and the Postgres database together.
- Postgres data is persisted in a Docker volume named `postgres_data`.
- The API routes and service behavior remain unchanged from the A1 copy.

## Run it

```bash
cd "A3 · Containerize your stack"
cp .env.example .env
docker compose up --build
```

Once the stack is running, the API is available at `http://localhost:8000`.

## Environment

Create `.env` from `.env.example`. The `.env` file is gitignored, while `.env.example` is committed.

## Persistence proof

1. Start the stack:
   ```bash
docker compose up --build
```
2. Create a task:
   ```bash
curl -X POST http://localhost:8000/tasks -H 'Content-Type: application/json' -d '{"title":"Persisted task"}'
```
3. Stop the app and container:
   ```bash
docker compose down
```
4. Start the stack again:
   ```bash
docker compose up --build
```
5. Confirm the task still exists:
   ```bash
curl http://localhost:8000/tasks
```

Because `postgres_data` is a named Docker volume, task rows survive container restarts.
