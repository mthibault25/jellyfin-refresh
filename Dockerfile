FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifest first (for caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . /app

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

# Use gunicorn for production-ish serving
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:5000", "--workers", "2"]
