# DragnCards Backend
# Clones the upstream repo, applies source patches at build time,
# then runs in dev mode (mix phx.server).

FROM elixir:1.14.4-slim AS backend

RUN apt-get update && \
    apt-get install -y git inotify-tools patch && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone DragnCards backend source
RUN git clone --depth 1 https://github.com/seastan/dragncards.git /tmp/dragncards && \
    cp -r /tmp/dragncards/backend/* /app/ && \
    cp -r /tmp/dragncards/backend/.formatter.exs /app/ 2>/dev/null || true && \
    rm -rf /tmp/dragncards

# Install hex and rebar
RUN mix local.hex --force && mix local.rebar --force

# Copy static files
COPY /backend/files/ /app

# Fetch and compile dependencies
RUN mix deps.get && mix deps.compile

# Copy entrypoint
COPY scripts/backend-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Plugin files will be mounted at /plugin/ via docker-compose volume
# (from the mc-plugin build)

ENV DB_HOSTNAME=postgres
ENV MIX_ENV=dev

EXPOSE 4000

ENTRYPOINT ["/app/entrypoint.sh"]
