FROM python:3.14.6-alpine

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

WORKDIR /app

COPY services/shared /shared
COPY services/history-service/pyproject.toml ./pyproject.toml
RUN uv sync --no-dev --no-install-project

COPY services/history-service/src ./src
RUN uv sync --no-dev

ENV PYTHONPATH=/app/src
ENV PATH=/app/.venv/bin:$PATH
ENV HTTP_PORT=4004

EXPOSE 4004

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:4004/health

CMD ["history-service"]
