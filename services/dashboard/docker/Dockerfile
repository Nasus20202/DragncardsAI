# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:24.16-alpine AS deps

ENV CI=true

RUN npm install -g pnpm@11.0.9 --no-fund --quiet

WORKDIR /app

COPY services/dashboard/package.json \
     services/dashboard/pnpm-lock.yaml \
     services/dashboard/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:24.16-alpine AS builder

ENV CI=true
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm install -g pnpm@11.0.9 --no-fund --quiet

WORKDIR /app

COPY services/dashboard/package.json \
     services/dashboard/pnpm-lock.yaml \
     services/dashboard/pnpm-workspace.yaml ./
COPY --from=deps /app/node_modules ./node_modules
COPY services/dashboard/ ./

RUN pnpm build

# ── Stage 3: runner ──────────────────────────────────────────────────────────
FROM node:24.16-alpine AS runner

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
