
.PHONY: help lint lint-fix test test-unit test-integration build up up-registry down down-clean \
	infra-up infra-down infra-restart smoke-up smoke-check smoke-model \
	run run-game-service run-agent-orchestrator run-dashboard

help:
	@printf "%s\n" \
		"make lint                       # check formatting and lint" \
		"make lint-fix                   # apply formatter/lint fixes" \
		"make test                       # run all tests" \
		"make test-unit                  # run unit tests" \
		"make test-integration           # run integration tests" \
		"make build                      # build docker images" \
		"make up                         # start docker stack" \
		"make up-registry                # pull GHCR images and start stack" \
		"make down                       # stop docker stack" \
		"make down-clean                 # stop stack and remove volumes" \
		"make infra-up                   # start infrastructure services only" \
		"make infra-down                 # stop infrastructure services only" \
		"make infra-restart              # restart infrastructure services only" \
		"make smoke-up                   # start stack with compose-managed smoke model" \
		"make smoke-check                # validate smoke dependencies" \
		"make smoke-model                # start compose-managed llama.cpp smoke model" \
		"make run                        # run local services directly" \
		"make run-game-service           # run game-service locally" \
		"make run-agent-orchestrator     # run agent-orchestrator locally" \
		"make run-dashboard              # run dashboard locally"

lint:
	./scripts/lint.sh

lint-fix:
	./scripts/lint.sh --fix

test:
	./scripts/test.sh all

test-unit:
	./scripts/test.sh unit

test-integration:
	./scripts/test.sh integration

build:
	./scripts/docker.sh build

up:
	./scripts/docker.sh start

up-registry:
	GAME_SERVICE_IMAGE=ghcr.io/nasus20202/dragncardsai/game-service:latest \
	AGENT_ORCHESTRATOR_IMAGE=ghcr.io/nasus20202/dragncardsai/agent-orchestrator:latest \
	DASHBOARD_IMAGE=ghcr.io/nasus20202/dragncardsai/dashboard:latest \
	DRAGNCARDS_MC_PLUGIN_IMAGE=ghcr.io/nasus20202/dragncardsai/dragncards-mc-plugin:latest \
	DRAGNCARDS_BACKEND_IMAGE=ghcr.io/nasus20202/dragncardsai/dragncards-backend:latest \
	DRAGNCARDS_FRONTEND_IMAGE=ghcr.io/nasus20202/dragncardsai/dragncards-frontend:latest \
	IMAGE_PULL_POLICY=always ./scripts/docker.sh start

down:
	./scripts/docker.sh down

down-clean:
	./scripts/docker.sh down-clean

infra-up:
	./scripts/docker-infrastructure.sh start

infra-down:
	./scripts/docker-infrastructure.sh stop

infra-restart:
	./scripts/docker-infrastructure.sh restart

smoke-up:
	./services/smoketest/smoke.sh up

smoke-check:
	./services/smoketest/smoke.sh check

smoke-model:
	./services/smoketest/smoke.sh model

run:
	./scripts/run.sh start

run-game-service:
	./scripts/run.sh start game-service

run-agent-orchestrator:
	./scripts/run.sh start agent-orchestrator

run-dashboard:
	./scripts/run.sh start dashboard
