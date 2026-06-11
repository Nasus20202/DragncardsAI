FROM python:3.14.6-alpine

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /app

# Copy lockfile and metadata first for layer caching
COPY services/game-service/pyproject.toml services/game-service/uv.lock ./

# Install dependencies only (not the project itself yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project
COPY services/game-service/src ./src
COPY external/dragncards-mc-plugin/fixtures/cerebro/cards.json /app/data/cards.json
COPY external/dragncards-mc-plugin/json /app/data/plugin-json
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
ENV PATH=/app/.venv/bin:$PATH
ENV DRAGNCARDS_CARDS_PATH=/app/data/cards.json
ENV DRAGNCARDS_MC_PLUGIN_JSON_DIR=/app/data/plugin-json

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8000/health

CMD ["game-service", "http"]
