FROM python:3.14.4-alpine

COPY --from=ghcr.io/astral-sh/uv:0.11.12 /uv /usr/local/bin/uv

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

CMD ["agent-orchestrator"]
