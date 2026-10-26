FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY cards ./cards

RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 cargo \
    && mkdir -p /data/storage \
    && chown cargo /data/storage

USER cargo

ENV STORAGE_DIR=/data/storage

EXPOSE 8000

CMD ["uvicorn", "app.web.application:build", "--factory", "--host", "0.0.0.0", "--port", "8000"]
