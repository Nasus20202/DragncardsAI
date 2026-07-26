FROM python:3.14.6-alpine

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

WORKDIR /app

COPY services/shared /shared
COPY services/eval-service/pyproject.toml ./pyproject.toml
RUN uv sync --no-dev --no-install-project

COPY services/eval-service/src ./src
COPY skills ./skills
RUN uv sync --no-dev

ENV PYTHONPATH=/app/src
ENV PATH=/app/.venv/bin:$PATH
ENV SKILL_ROOTS=/app/skills
ENV HTTP_PORT=4005

EXPOSE 4005

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:4005/health

CMD ["eval-service"]
