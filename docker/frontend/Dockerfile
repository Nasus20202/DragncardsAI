# DragnCards Frontend
# Clones the upstream repo and installs dependencies at build time
# for faster container startup. Runs the React dev server.

FROM node:24.14-alpine AS frontend

RUN apk add --no-cache git

WORKDIR /app

# Clone DragnCards frontend source
RUN git clone --depth 1 https://github.com/seastan/dragncards.git /tmp/dragncards && \
    cp -r /tmp/dragncards/frontend/* /app/ && \
    cp -r /tmp/dragncards/frontend/.env* /app/ 2>/dev/null || true && \
    rm -rf /tmp/dragncards

# Install dependencies at build time (cached layer)
RUN npm install --legacy-peer-deps

# Pre-generate tailwind.compiled.css so webpack doesn't fail on first start
# (start:docker runs postcss and webpack in parallel; webpack resolves the
# import before postcss can write the file if we don't do this first)
RUN npx postcss src/css/tailwind.src.css -o src/css/tailwind.compiled.css

# Copy entrypoint
COPY scripts/frontend-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV REACT_APP_BE_HOSTNAME=backend

EXPOSE 3000

ENTRYPOINT ["/app/entrypoint.sh"]
