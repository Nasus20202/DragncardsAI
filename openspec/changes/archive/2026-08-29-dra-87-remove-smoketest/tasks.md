# Tasks: Remove Smoketest Package and CI llama.cpp Smoke Runner

- [x] 1. Remove smoketest package and CI configuration
  - [x] 1.1 Delete `services/smoketest/` directory.
  - [x] 1.2 Remove smoketest steps, cache, and execution from `.github/workflows/test.yaml`.
  - [x] 1.3 Remove `llama-cpp-smoke` and `llama-cpp-smoke-model-cache` from `docker-compose.yaml`.
- [x] 2. Remove auxiliary scripts, Makefile targets, and documentation
  - [x] 2.1 Remove smoke targets from `Makefile`.
  - [x] 2.2 Remove smoketest formatting from `scripts/lint.sh`.
  - [x] 2.3 Update `README.md` to remove smoketest references.
- [x] 3. Validation and QA
  - [x] 3.1 Run `./scripts/lint.sh --fix`.
  - [x] 3.2 Run `./scripts/test.sh unit`.
  - [x] 3.3 Run `openspec validate --all`.
