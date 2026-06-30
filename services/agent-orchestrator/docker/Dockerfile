FROM python:3.14.6-alpine

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv

WORKDIR /app

COPY services/agent-orchestrator/pyproject.toml ./pyproject.toml
RUN uv sync --no-dev --no-install-project

COPY services/agent-orchestrator/src ./src
COPY skills ./skills
RUN uv sync --no-dev

ENV PYTHONPATH=/app/src
ENV PATH=/app/.venv/bin:$PATH
ENV AGENT_ORCHESTRATOR_SKILL_ROOTS=/app/skills

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=10s --retries=5 \
  CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8010/health

CMD ["agent-orchestrator"]
