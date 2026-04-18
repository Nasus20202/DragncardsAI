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
cd services/game-service
python -m pytest tests/unit/ -v

# Rebuild images
cd docker
docker compose build
```
