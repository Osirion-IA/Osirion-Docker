# =============================================================================
# Osirion-Frontend — Dockerfile multi-stage
# =============================================================================
# Stage 1 : deps     — installation des dépendances de production
# Stage 2 : builder  — build Next.js (output standalone)
# Stage 3 : runner   — image finale minimale (~200 MB)
#
# Pré-requis : next.config.mjs doit avoir output: 'standalone'
#
# Usage :
#   docker build -t osirion-frontend .
#   docker run -p 3000:3000 --env-file .env osirion-frontend
# =============================================================================

# -----------
# Stage 1 : deps — dépendances de production uniquement
# -----------
FROM node:20-alpine AS deps

RUN apk add --no-cache libc6-compat

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# -----------
# Stage 2 : builder — build complet Next.js
# -----------
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build && mkdir -p /app/public

# -----------
# Stage 3 : runner — image finale minimale
# -----------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Utilisateur non-root pour la sécurité
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Assets statiques publics
COPY --from=builder /app/public ./public

# Build standalone : server.js + node_modules minimaux
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
# Fichiers statiques Next.js (_next/static)
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["node", "server.js"]
