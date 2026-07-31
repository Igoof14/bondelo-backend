FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Dependencies first: this layer is cached until the lockfile changes.
# Plain COPY/RUN rather than --mount: Cloud Build runs the legacy builder,
# which does not support BuildKit mounts.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . /app
RUN uv sync --frozen --no-dev


FROM python:3.13-slim

# SSL_TBANK_VERIFY makes the T-Invest SDK use the Russian Trusted Root CA it ships with;
# no default trust store has it, so without this every broker call fails the handshake.
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" SSL_TBANK_VERIFY=true
RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY --from=builder --chown=app:app /app /app
USER app

# Cloud Run injects PORT and provides concurrency itself, so a single worker is right.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
