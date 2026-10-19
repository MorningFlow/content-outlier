FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (curl, ffmpeg for transcription if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create media directory for local storage backend
RUN mkdir -p /app/media_storage

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
