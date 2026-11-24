FROM node:22-slim AS deps

WORKDIR /app/web

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:22-slim AS builder

WORKDIR /app/web

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /app/web/node_modules ./node_modules
COPY . .

ARG API_ORIGIN=http://localhost:8000
ENV API_ORIGIN=$API_ORIGIN

RUN --mount=type=cache,target=/app/web/.next/cache npx next build

FROM node:22-slim AS runner

WORKDIR /app/web

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# Runtime ownership: copy with --chown so Next.js can write its cache at runtime
COPY --from=builder --chown=node:node /app/web/public ./public
COPY --from=builder --chown=node:node /app/web/.next/standalone ./
COPY --from=builder --chown=node:node /app/web/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]