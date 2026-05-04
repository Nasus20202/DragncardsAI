# DragncardsAI

An LLM-powered bot that plays **Marvel Champions** on [DragnCards](https://github.com/seastan/dragncards).

## Quick start

```bash
cd docker
docker compose up -d
```

| Service      | URL                             |
| ------------ | ------------------------------- |
| Frontend     | http://localhost:3000           |
| Backend API  | http://localhost:4000           |
| Game Service | http://localhost:8000           |
| Login        | dev_user@example.com / password |

## Development

```bash
# Unit tests (no network required)
scripts/test.sh unit

# Integration tests (requires Docker stack running)
scripts/test.sh integration

# Rebuild images
scripts/docker.sh build
```
