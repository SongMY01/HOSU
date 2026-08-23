FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Build SQLite database from raw CSVs
RUN python 1_data_infrastructure/pipeline/build.py

# Expose port and run unified ASGI server (Flask REST + Remote MCP SSE)
ENV PORT=5050
ENV PYTHONUNBUFFERED=1
EXPOSE $PORT

CMD ["sh", "-c", "uvicorn asgi:app --host 0.0.0.0 --port ${PORT:-5050} --timeout-keep-alive 120"]
