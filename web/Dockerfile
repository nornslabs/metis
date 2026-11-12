# Stage 1: install Node dependencies
FROM node:22-slim AS deps

WORKDIR /app/web

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Stage 2: build Next.js standalone output
FROM node:22-slim AS builder

WORKDIR /app/web

COPY --from=deps /app/web/node_modules ./node_modules
COPY . .

ENV NODE_ENV=production
RUN npx next build

# Stage 3: run
FROM node:22-slim AS runner

WORKDIR /app/web

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

COPY --from=builder /app/web/public ./public
RUN mkdir -p .next && chown -R node:node .next

COPY --from=builder /app/web/.next/standalone ./
COPY --from=builder /app/web/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
