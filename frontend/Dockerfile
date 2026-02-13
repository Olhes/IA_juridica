FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package-lock.json ./frontend/

RUN npm ci && npm --prefix frontend ci

COPY frontend ./frontend
RUN npm --prefix frontend run build

FROM node:20-alpine AS runtime

WORKDIR /app/frontend

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

COPY --from=builder /app/frontend ./
RUN npm prune --omit=dev

EXPOSE 3000

CMD ["npm", "run", "start"]
