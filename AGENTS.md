# DragncardsAI Agent Guide

Read this file before making changes in this repository.

## Scope

These instructions apply to the whole repository unless a deeper `AGENTS.md` overrides them.

## Project Overview

- This repository contains an LLM-powered Marvel Champions bot for DragnCards.
- Top-level areas include `services/`, `scripts/`, `external/`, `openspec/`, and `.github/`.
- Primary local workflows are documented in `README.md`.

## Useful Reading

- Start with [`README.md`](README.md) for local setup, test commands, and service URLs.
- Read [`services/game-service/README.md`](services/game-service/README.md) when working on DragnCards session control, MCP tools, or game actions.
- Read [`services/agent-orchestrator/README.md`](services/agent-orchestrator/README.md) when working on agent sessions, skills, providers, or background jobs.
- Read files nearest to the change before introducing new patterns.

## Service-Level Guides

Service-specific AGENTS.md files override these instructions:

- [`services/dashboard/AGENTS.md`](services/dashboard/AGENTS.md) - Frontend development with Hero UI components
- [`services/game-service/AGENTS.md`](services/game-service/AGENTS.md) - Game service patterns, DragnLang actions, Phoenix Channels
- [`services/agent-orchestrator/AGENTS.md`](services/agent-orchestrator/AGENTS.md) - Session lifecycle, jobs, provider configuration

## Working Rules

- Prefer the smallest correct change that fits the existing code style.
- Check nearby code before introducing new abstractions, helpers, or patterns.
- Do not revert or overwrite user changes that are unrelated to your task.
- Keep secrets out of commits and examples.

## Repo Conventions

- Use `scripts/test.sh unit` for unit tests.
- Use `scripts/test.sh integration` for integration tests when the Docker stack is running.
- Use `scripts/docker.sh build` when a rebuild is needed.
- Follow existing structure inside each service instead of forcing one pattern across the monorepo.

## Agent Guidance

- Start by reading `README.md` and the files closest to the requested change.
- When working in `openspec/`, preserve the existing OpenSpec workflow and artifact format.
- When working in `external/`, treat vendored or upstream code carefully and avoid unnecessary edits.
- Explain assumptions briefly when behavior is ambiguous.
- Before finishing a task, you are expected to run:
  - `./scripts/lint.sh --fix`
  - `./scripts/test.sh unit`
  - `./scripts/docker-infrastructure.sh start` followed by `./scripts/test.sh integration`
