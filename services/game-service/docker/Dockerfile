FROM python:3.14.4-alpine

COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /usr/local/bin/uv

WORKDIR /app

# Copy lockfile and metadata first for layer caching
COPY services/game-service/pyproject.toml services/game-service/uv.lock ./

# Install dependencies only (not the project itself yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project
COPY services/game-service/src ./src
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["uv", "run", "game-service", "http"]
