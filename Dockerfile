# Dockerfile
FROM python:3.12-slim

# Prevent .pyc files + ensure logs flush
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working dir
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Expose Flask port
EXPOSE ${FLASK_PORT}

CMD ["python", "-u", "app.py"]

# Gunicorn for production-ish serving
# CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${FLASK_PORT:-5050} -- workers 2 -- threads 4 --timeout 120 app:app"]
