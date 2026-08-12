# A5 · Background Jobs with Celery

Professional async job processing: accept fast (202), work in background, report status.

## Overview

This assignment implements the professional pattern for slow operations:
- **Accept instantly**: Endpoint returns 202 Accepted with job ID
- **Work in background**: Celery worker processes long-running tasks
- **Report status**: Dedicated status endpoint tracks job progress
- **Handles failures**: Automatic retries, idempotency, error tracking
- **Production-ready**: Alerts, logging, and comprehensive monitoring

## Features

- **Async Task Queue**: Celery + Redis for reliable job processing
- **PDF Analysis**: AI-powered document analysis with text extraction
- **Job Status Tracking**: Monitor task progress in real-time
- **Automatic Retries**: 3 retry attempts with exponential backoff
- **Idempotency**: Jobs won't run twice even if request retried
- **Error Handling**: Graceful failure with detailed error messages
- **JWT Authentication**: Secure job endpoints
- **Database Persistence**: Results stored in PostgreSQL
- **Comprehensive Tests**: 10+ test cases covering all scenarios

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌──────────────┐
│   FastAPI   │────────▶│   Redis      │◀────────│   Celery     │
│  (Sync)     │ Enqueue │   Queue      │ Workers │   Workers    │
└─────────────┘         └──────────────┘         └──────────────┘
       │                                                │
       │ Poll Status                                   │
       └──────────────────────────────────────────────▶│
              ◀──────────────────────────────────────────
                     Update PostgreSQL
```

## API Endpoints

### 1. Analyze PDF (Async)
**POST /analyze-pdf**

Submit a PDF for AI analysis. Returns immediately with job ID.

**Request:**
```bash
curl -X POST http://localhost:8000/analyze-pdf \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -F "analysis_type=summary"
```

**Response (202 Accepted):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Analysis started. Check status endpoint for updates."
}
```

### 2. Job Status
**GET /jobs/{job_id}**

Check the status of a submitted job.

**Response (while processing):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 45,
  "message": "Extracting text from pages..."
}
```

**Response (completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "success",
  "result": {
    "summary": "Document discusses Q4 financials...",
    "key_points": ["Revenue up 15%", "Costs reduced", "..."],
    "pages_analyzed": 12,
    "confidence": 0.92
  },
  "completed_at": "2024-01-15T10:35:00Z"
}
```

**Response (failed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": "PDF parsing failed: corrupted file",
  "retries_remaining": 2,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 3. List Jobs
**GET /jobs**

List all jobs for the authenticated user.

**Response:**
```json
{
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "success",
      "created_at": "2024-01-15T10:30:00Z",
      "completed_at": "2024-01-15T10:35:00Z"
    },
    {
      "job_id": "660e8400-e29b-41d4-a716-446655440001",
      "status": "processing",
      "created_at": "2024-01-15T10:40:00Z"
    }
  ]
}
```

## Running Locally

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Redis (required for Celery)
```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or locally (if installed)
redis-server
```

### 3. Set environment variables
```bash
export OPENAI_API_KEY="sk-..."
export JWT_SECRET_KEY="your-secret-key"
export DATABASE_URL="postgresql://todo:todo@localhost:5432/tasks"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
```

### 4. Initialize database
```bash
python -c "from repository import TaskRepository; TaskRepository().init_db()"
```

### 5. Start FastAPI server
```bash
uvicorn main:app --reload
```

### 6. Start Celery worker (in another terminal)
```bash
celery -A celery_app worker --loglevel=info
```

### 7. (Optional) Start Flower monitoring dashboard
```bash
celery -A celery_app flower
# Visit http://localhost:5555
```

## Running with Docker

```bash
# Build and start all services
docker-compose up --build

# Run tests
docker-compose exec app pytest tests/test_main.py -v

# View Celery tasks in Flower (Celery monitoring)
# Visit http://localhost:5555

# View logs
docker-compose logs -f app
docker-compose logs -f celery-worker
docker-compose logs -f redis
```

## Task Flow

### PDF Analysis Task
1. **Accept (202)**: User uploads PDF, gets job ID immediately
2. **Extract**: Worker extracts text from PDF pages
3. **Analyze**: AI analyzes content using OpenAI
4. **Categorize**: AI categorizes findings
5. **Store**: Results saved to PostgreSQL
6. **Report**: User can query status/results anytime

### Retry Logic
- **Automatic retries**: 3 attempts with exponential backoff
- **Backoff**: 1s, 2s, 4s delays between retries
- **Idempotency**: Uses job_id to prevent duplicate processing
- **Dead letter queue**: Failed jobs logged for investigation

## Database Schema

### jobs table
```sql
CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID UNIQUE NOT NULL,
    user_id INTEGER REFERENCES users(id),
    job_type TEXT NOT NULL,  -- 'pdf_analysis', etc.
    status TEXT NOT NULL,     -- 'pending', 'processing', 'success', 'failed'
    progress INTEGER DEFAULT 0,
    input_data JSONB,
    result_data JSONB,
    error_message TEXT,
    retries_remaining INTEGER DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_job_id ON jobs(job_id);
CREATE INDEX idx_jobs_status ON jobs(status);
```

## Testing

```bash
pytest tests/test_main.py -v

# Test categories:
# 1. Authentication
# 2. Job submission (returns 202)
# 3. Job status tracking
# 4. PDF parsing
# 5. AI analysis
# 6. Retry logic
# 7. Idempotency
# 8. Error handling
# 9. Database persistence
# 10. Concurrent jobs
```

## Key Concepts

### Idempotency
Every job has a unique `job_id` (UUID). If a client retries submission:
- Same `job_id` in request means same job
- Worker won't process twice
- Returns existing result

### Retries
Jobs automatically retry on failure:
```python
@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,),
                  retry_backoff=True, retry_backoff_max=600, retry_jitter=True)
def analyze_pdf_task(self, job_id, ...):
    # Auto-retries on Exception with exponential backoff
```

### Status Tracking
Every state change is logged:
- `pending` → submitted, waiting for worker
- `processing` → worker actively processing
- `success` → completed with results
- `failed` → max retries exceeded

### Error Handling
Detailed error tracking:
- Error message stored with job
- Stack trace logged to system
- Retries remaining tracked
- User notified of failures

## Production Checklist

- ✅ Celery broker (Redis) with persistence
- ✅ Multiple worker processes
- ✅ Task timeouts (30s default)
- ✅ Dead letter queue for dead tasks
- ✅ Job result retention policy (30 days)
- ✅ Monitoring with Flower or Prometheus
- ✅ Log aggregation (ELK stack recommended)
- ✅ Alert on task failures
- ✅ Job prioritization queues
- ✅ Rate limiting on submissions

## Troubleshooting

### Worker not processing tasks
```bash
# Check Redis connection
redis-cli ping  # Should return PONG

# Check worker is running
celery -A celery_app inspect active

# View worker logs
celery -A celery_app worker --loglevel=debug
```

### Jobs stuck in pending
```bash
# Purge queue and restart
celery -A celery_app purge
docker-compose restart celery-worker
```

### Memory issues
```bash
# Set worker max tasks per child (prevent memory leaks)
celery -A celery_app worker --max-tasks-per-child=1000
```

## Files

- `main.py` - FastAPI application with async endpoints
- `celery_app.py` - Celery configuration and task definitions
- `ai_service.py` - OpenAI integration for PDF analysis
- `repository.py` - Database operations for jobs table
- `auth.py` - JWT authentication (from A4)
- `docker-compose.yml` - Multi-container setup (app, worker, Redis, PostgreSQL)
- `tests/test_main.py` - Comprehensive test suite
