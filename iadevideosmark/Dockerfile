# syntax=docker/dockerfile:1

########################
# API image (python)
########################
FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# FFmpeg is needed for mock video rendering and some pipelines.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install -r /app/apps/api/requirements.txt

# App code
COPY apps /app/apps
COPY config /app/config
RUN mkdir -p /app/outputs
COPY scripts /app/scripts
COPY docker-compose.yml /app/docker-compose.yml
COPY Dockerfile /app/Dockerfile

EXPOSE 8000
CMD ["python","-m","uvicorn","apps.api.main:app","--host","0.0.0.0","--port","8000"]

########################
# Web dev image (vite)
########################
FROM node:20-slim AS web_dev
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json* apps/web/pnpm-lock.yaml* apps/web/yarn.lock* /app/apps/web/
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY apps/web /app/apps/web
EXPOSE 5173
CMD ["npm","run","dev","--","--host","0.0.0.0","--port","5173"]

########################
# Logs viewer (python)
########################
FROM api AS logs
EXPOSE 8080
CMD ["python","-m","apps.logging_service.main"]

