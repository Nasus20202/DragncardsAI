FROM python:3.14.7-alpine

COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

WORKDIR /app

COPY services/shared /shared
COPY services/history-service/pyproject.toml services/history-service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/history-service/src ./src
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
ENV PATH=/app/.venv/bin:$PATH
ENV HTTP_PORT=4004

EXPOSE 4004

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:4004/health

CMD ["history-service"]
