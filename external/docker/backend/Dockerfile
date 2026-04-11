# DragnCards Backend
# Copies backend source from the dragncards git submodule (external/dragncards).

FROM elixir:1.14.5-otp-25-alpine AS backend

RUN apk add --no-cache inotify-tools build-base git

WORKDIR /app

# Copy DragnCards backend source from submodule
COPY external/dragncards/backend/ /app/

# Install hex and rebar
RUN mix local.hex --force && mix local.rebar --force

# Copy static config and seed files
COPY external/docker/backend/files/ /app

# Fetch and compile dependencies
RUN mix deps.get && mix deps.compile

# Copy entrypoint
COPY external/docker/scripts/backend-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Plugin files will be mounted at /plugin/ via docker-compose volume
# (from the mc-plugin build)

ENV DB_HOSTNAME=postgres
ENV MIX_ENV=dev

EXPOSE 4000

ENTRYPOINT ["/app/entrypoint.sh"]
