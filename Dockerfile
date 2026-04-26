FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder

WORKDIR /app

# Install runtime AND build dependencies
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

# Create venv and install dependencies
RUN uv venv /venv
ENV VIRTUAL_ENV=/venv \
    PATH="/venv/bin:$PATH"
RUN uv sync --locked --no-dev

FROM python:3.13-slim

# Runtime dependencies only (smaller final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libxrender1 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /venv /venv

ENV VIRTUAL_ENV=/venv \
    PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /data

COPY main.py .

ENTRYPOINT ["python", "main.py"]
