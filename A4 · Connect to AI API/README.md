# A4 · Connect to AI API

Integration of LLM (Large Language Model) with FastAPI using OpenAI and LangChain.

## Overview

This assignment adds one endpoint to the API that uses an AI model for intelligent analysis. The endpoint:
- Accepts text input with a task description
- Uses OpenAI's GPT to analyze and categorize the task
- Returns structured analysis with schema validation
- Includes retry logic, timeouts, and comprehensive error handling
- Is backed by authentication and database persistence

## Features

- **JWT Authentication**: Reuses auth from previous assignment
- **AI Analysis Endpoint**: `/analyze-task` - classifies and analyzes task descriptions
- **Schema Validation**: Pydantic models ensure all responses are structured
- **Robust Error Handling**: Timeouts (30s), retries (3 attempts), exponential backoff
- **Database Persistence**: Stores analysis results in PostgreSQL
- **Comprehensive Tests**: 8+ test cases covering success and failure scenarios

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="your-api-key"
export JWT_SECRET_KEY="your-secret"
export DATABASE_URL="postgresql://todo:todo@localhost:5432/tasks"

# Run migrations
python main.py

# Start the server
uvicorn main:app --reload
```

## Running with Docker

```bash
# Build and run
docker-compose up --build

# Run tests
docker-compose exec app pytest tests/test_main.py -v
```

## API Endpoints

### Analysis Endpoint
**POST /analyze-task**

Analyze and categorize a task description using AI.

**Request:**
```json
{
  "task_description": "Review the Q4 budget proposal and provide recommendations"
}
```

**Response (200):**
```json
{
  "id": 123,
  "analysis": {
    "task_type": "review",
    "category": "finance",
    "priority": "high",
    "estimated_time_minutes": 60,
    "key_points": ["budget proposal review", "provide recommendations"],
    "confidence": 0.95
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Database Schema

### analyses table
- id: SERIAL PRIMARY KEY
- user_id: INTEGER FOREIGN KEY
- task_description: TEXT
- task_type: TEXT
- category: TEXT
- priority: TEXT (low, medium, high)
- estimated_time_minutes: INTEGER
- key_points: TEXT[] (ARRAY)
- confidence: FLOAT
- created_at: TIMESTAMPTZ

## Testing

```bash
pytest tests/test_main.py -v

# Test categories:
# 1. Authentication and authorization
# 2. Valid analysis requests
# 3. Schema validation
# 4. Timeout handling
# 5. Retry logic
# 6. Database persistence
# 7. Error responses
# 8. Concurrent requests
```

## Implementation Details

### AI Service Integration
- Uses LangChain for reliable LLM interactions
- OpenAI GPT-3.5/GPT-4 for natural language processing
- Structured output using Pydantic schemas

### Reliability Features
- **Timeouts**: 30-second maximum wait per request
- **Retries**: Up to 3 attempts with exponential backoff (1s, 2s, 4s)
- **Circuit Breaking**: Graceful degradation on repeated failures
- **Validation**: Every AI response validated against schema before returning

### Security
- JWT token-based authentication on all routes
- Rate limiting considerations for AI API costs
- Secure storage of analysis results
- Environment variable management for API keys
