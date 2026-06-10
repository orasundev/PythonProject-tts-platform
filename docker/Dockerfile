FROM python:3.12-slim

# System dependencies for pydub (ffmpeg), lxml, asyncpg, bcrypt
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libxml2-dev \
    libxslt-dev \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
