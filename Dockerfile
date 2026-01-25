FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
  && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN python -m pip install --upgrade pip && pip install -r /app/apps/api/requirements.txt

COPY . /app

EXPOSE 8000
CMD ["python","-m","uvicorn","apps.api.main:app","--host","0.0.0.0","--port","8000"]
