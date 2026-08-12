#!/bin/bash
# Quick start script for A5 Background Jobs

echo "=========================================="
echo "A5: Background Jobs with Celery - Quick Start"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Step 1: Create .env file${NC}"
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env (Update OPENAI_API_KEY)${NC}"
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi
echo ""

echo -e "${BLUE}Step 2: Start Docker services${NC}"
echo "Running: docker-compose up --build"
echo ""
echo "This will start:"
echo "  - PostgreSQL (port 5436)"
echo "  - Redis (port 6379)"
echo "  - FastAPI app (port 8001)"
echo "  - Celery worker"
echo "  - Flower monitoring (port 5555)"
echo ""

docker-compose up --build

echo ""
echo -e "${GREEN}=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "API Documentation:"
echo "  http://localhost:8001/docs"
echo ""
echo "Flower (Celery Monitoring):"
echo "  http://localhost:5555"
echo ""
echo "Test the API:"
echo ""
echo "1. Create account:"
echo "  curl -X POST http://localhost:8001/auth/signup \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"test@example.com\",\"password\":\"password123\"}'"
echo ""
echo "2. Login:"
echo "  TOKEN=\$(curl -X POST http://localhost:8001/auth/login \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"test@example.com\",\"password\":\"password123\"}' | jq -r '.access_token')"
echo ""
echo "3. Submit analysis:"
echo "  curl -X POST http://localhost:8001/analyze-text \\"
echo "    -H \"Authorization: Bearer \$TOKEN\" \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"text\":\"This is a test document for AI analysis purposes.\"}'"
echo ""
echo "4. Check status (replace JOB_ID):"
echo "  curl -X GET http://localhost:8001/jobs/JOB_ID \\"
echo "    -H \"Authorization: Bearer \$TOKEN\""
echo ""
echo -e "${NC}"
