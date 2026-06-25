# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.5.21-python3.13-bookworm-slim AS builder

WORKDIR /app

# Build-time dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxrender1 \
    libxi6 \
    g++ \
    gcc \
    cmake \
    make \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

# Create venv and install dependencies (project source not needed yet)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# ---- Final stage ----
FROM python:3.13-slim

# Runtime-only dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxrender1 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /venv

ENV VIRTUAL_ENV=/venv \
    PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY main.py .
COPY settings.py config.toml /app/
COPY src/ /app/src/

ENTRYPOINT ["python", "main.py"]
