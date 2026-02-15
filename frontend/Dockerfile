FROM node:24-alpine AS builder

WORKDIR /app

RUN corepack enable

COPY package.json ./
COPY frontend/package.json frontend/pnpm-lock.yaml ./frontend/

RUN pnpm --dir frontend install --frozen-lockfile

COPY frontend ./frontend
RUN pnpm --dir frontend run build

FROM node:24-alpine AS runtime

WORKDIR /app/frontend

RUN corepack enable

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

COPY --from=builder /app/frontend ./

EXPOSE 3000

CMD ["pnpm", "run", "start"]
