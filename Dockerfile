FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
COPY bot/ ./bot/
RUN uv sync --frozen --no-dev

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

CMD ["python", "-m", "bot.main"]
