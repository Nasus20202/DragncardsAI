FROM python:3.14-alpine

WORKDIR /app

# Copy package metadata and install dependencies first (layer caching)
COPY services/game-service/pyproject.toml ./
COPY services/game-service/src ./src

# Install the package (editable-like install with all deps)
RUN pip install --no-cache-dir .

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["game-service", "http"]
