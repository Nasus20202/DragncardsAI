FROM python:3.14.7-alpine

COPY --from=ghcr.io/astral-sh/uv:0.12.2 /uv /usr/local/bin/uv

WORKDIR /app

COPY services/shared /shared
COPY services/eval-service/pyproject.toml services/eval-service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/eval-service/src ./src
COPY skills ./skills
RUN uv sync --frozen --no-dev

ENV PYTHONPATH=/app/src
ENV PATH=/app/.venv/bin:$PATH
ENV SKILL_ROOTS=/app/skills
ENV HTTP_PORT=4005

EXPOSE 4005

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:4005/health

CMD ["eval-service"]
