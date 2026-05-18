FROM python:3.12-slim

# WeasyPrint system dependencies (Debian 12 Bookworm)
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libharfbuzz0b \
    libfontconfig1 \
    fonts-liberation \
    shared-mime-info \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crear directorio de config si no existe (para app_config.json)
RUN mkdir -p config

ENV PYTHONUNBUFFERED=1

# Railway inyecta PORT automaticamente; gunicorn lo usa
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 300 --access-logfile - app:app
