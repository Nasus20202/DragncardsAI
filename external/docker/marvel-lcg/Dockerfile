# Marvel Champions Digital: Ronin Edition
# Build from the pinned external/marvel-lcg submodule with the repository root
# as the Docker build context. Card art is deliberately not copied into this
# image; the platform downloads it into the runtime asset volume on demand.

FROM node:24.20.0-alpine AS frontend

WORKDIR /build
COPY external/marvel-lcg/public/js ./public/js

RUN corepack enable && \
    pnpm dlx --package=typescript tsc --project public/js/tsconfig.json

FROM python:3.14.7-alpine

ENV HOME=/tmp

WORKDIR /app

COPY external/marvel-lcg/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    addgroup -g 10001 marvel-lcg && \
    adduser -D -u 10001 -G marvel-lcg \
        -h /app -H -s /sbin/nologin marvel-lcg && \
    install -d -o 10001 -g 10001 -m 0700 /run/marvel-lcg

# Copy only runtime source from the submodule. In particular, do not copy its
# asset cache, replay files, or runtime state into the image.
COPY external/marvel-lcg/core ./core
COPY external/marvel-lcg/cards ./cards
COPY external/marvel-lcg/data ./data
COPY external/marvel-lcg/deck ./deck
COPY external/marvel-lcg/engine ./engine
COPY external/marvel-lcg/game ./game
COPY external/marvel-lcg/public ./public
COPY external/marvel-lcg/build.py ./build.py
COPY external/marvel-lcg/main.py ./main.py
COPY --from=frontend /build/public/js ./public/js

COPY external/docker/marvel-lcg/entrypoint.sh /usr/local/bin/marvel-lcg-entrypoint
RUN chmod 0755 /usr/local/bin/marvel-lcg-entrypoint

EXPOSE 2345

USER 10001:10001

ENTRYPOINT ["/usr/local/bin/marvel-lcg-entrypoint"]
