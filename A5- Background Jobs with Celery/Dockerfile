FROM python:3.12-slim

# Copy the official uv binary directly into your image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies with uv system-wide
RUN uv pip install --system --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
