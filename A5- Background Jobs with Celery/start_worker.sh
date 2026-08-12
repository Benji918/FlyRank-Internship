#!/bin/bash
# Celery Worker Startup Script
# Run background job workers for task processing

set -e

echo "Starting Celery Worker..."
echo "Broker: $CELERY_BROKER_URL"
echo "Backend: $CELERY_RESULT_BACKEND"

# Start with concurrency of 4 and max tasks per child to prevent memory leaks
celery -A celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --max-tasks-per-child=1000 \
    --time-limit=1800 \
    --soft-time-limit=1700 \
    --without-gossip \
    --without-mingle \
    --without-heartbeat
