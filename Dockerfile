FROM python:3.12-slim

ARG APP_VERSION=dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY cards ./cards

RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --create-home --home-dir /home/cargo cargo \
    && mkdir -p /data/storage \
    && chown cargo /data/storage

USER cargo

ENV STORAGE_DIR=/data/storage \
    HOME=/home/cargo

EXPOSE 8000

CMD ["uvicorn", "app.web.application:build", "--factory", "--host", "0.0.0.0", "--port", "8000"]
