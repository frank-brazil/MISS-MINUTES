# MISSMINUTES Dockerfile
# NOTE: GUI/avatar features require a display server and are NOT supported
# in containers. This Dockerfile is for headless/API-only deployment.

FROM python:3.13-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY requirements.txt ./
COPY config/ config/
COPY app/ app/
COPY main.py ./
COPY data/ data/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p data/memory data/documents data/evaluation logs

# Environment defaults
ENV MISSMINUTES_HOST=0.0.0.0
ENV MISSMINUTES_PORT=8000
ENV MISSMINUTES_LOG_LEVEL=INFO
ENV MISSMINUTES_ENV=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
