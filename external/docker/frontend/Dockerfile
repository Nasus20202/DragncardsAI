# DragnCards Frontend
# Copies frontend source from the dragncards git submodule (external/dragncards).
# Installs dependencies at build time for faster container startup. Runs the React dev server.

FROM node:24.14-alpine AS frontend

WORKDIR /app

# Copy DragnCards frontend source from submodule
COPY external/dragncards/frontend/ /app/

# Install dependencies at build time (cached layer)
RUN npm install --legacy-peer-deps

# Pre-generate tailwind.compiled.css so webpack doesn't fail on first start
# (start:docker runs postcss and webpack in parallel; webpack resolves the
# import before postcss can write the file if we don't do this first)
RUN npx postcss src/css/tailwind.src.css -o src/css/tailwind.compiled.css

# Copy entrypoint
COPY external/docker/scripts/frontend-entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV REACT_APP_BE_HOSTNAME=backend

EXPOSE 3000

ENTRYPOINT ["/app/entrypoint.sh"]
