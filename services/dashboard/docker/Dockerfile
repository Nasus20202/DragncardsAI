# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:24.19.0-alpine AS deps

ENV CI=true

RUN corepack enable

WORKDIR /app

COPY services/dashboard/package.json \
     services/dashboard/pnpm-lock.yaml \
     services/dashboard/pnpm-workspace.yaml ./

RUN corepack install

RUN --mount=type=cache,id=pnpm,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:24.19.0-alpine AS builder

ENV CI=true
ENV NEXT_TELEMETRY_DISABLED=1

RUN corepack enable

WORKDIR /app

COPY services/dashboard/package.json \
     services/dashboard/pnpm-lock.yaml \
     services/dashboard/pnpm-workspace.yaml ./

RUN corepack install

COPY --from=deps /app/node_modules ./node_modules
COPY services/dashboard/ ./

RUN pnpm build

# ── Stage 3: runner ──────────────────────────────────────────────────────────
FROM node:24.19.0-alpine AS runner

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

WORKDIR /app

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static     ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public           ./public

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
