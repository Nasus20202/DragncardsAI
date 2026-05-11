
.PHONY: help lint lint-fix test test-unit test-integration build up down \
	infra-up infra-down infra-restart \
	run run-game-service run-agent-orchestrator run-dashboard

help:
	@printf "%s\n" \
		"make lint               # check formatting and lint" \
		"make lint-fix           # apply formatter/lint fixes" \
		"make test               # run all tests" \
		"make test-unit          # run unit tests" \
		"make test-integration   # run integration tests" \
		"make build              # build docker images" \
		"make up                 # start docker stack" \
		"make down               # stop docker stack" \
		"make infra-up           # start infrastructure services only" \
		"make infra-down         # stop infrastructure services only" \
		"make infra-restart      # restart infrastructure services only" \
		"make run                # run local services directly" \
		"make run-game-service   # run game-service locally" \
		"make run-agent-orchestrator" \
		"make run-dashboard"

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

down:
	./scripts/docker.sh down

infra-up:
	./scripts/docker-infrastructure.sh start

infra-down:
	./scripts/docker-infrastructure.sh stop

infra-restart:
	./scripts/docker-infrastructure.sh restart

run:
	./scripts/run.sh start

run-game-service:
	./scripts/run.sh start game-service

run-agent-orchestrator:
	./scripts/run.sh start agent-orchestrator

run-dashboard:
	./scripts/run.sh start dashboard
