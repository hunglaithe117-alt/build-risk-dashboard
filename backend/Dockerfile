FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for git, build tools, and ML runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    curl \
    unzip \
    libgomp1 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for Python package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Default command: run the API server
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
