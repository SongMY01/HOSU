FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Build SQLite database from raw CSVs
RUN python song/1_data_infrastructure/pipeline/build.py

# Expose port and run gunicorn
ENV PORT=5050
ENV PYTHONUNBUFFERED=1
EXPOSE $PORT

CMD ["sh", "-c", "gunicorn --chdir song/2_regional_service app:app --bind 0.0.0.0:${PORT:-5050} --timeout 120 --workers 2"]
