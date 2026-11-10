# ChessClass web (S-30): сборка Vite -> статика nginx с прокси /api.
# syntax=docker/dockerfile:1

FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# S-58: стадия в бренде (prod по умолчанию; staging-образ передаёт APP_STAGE=staging).
ARG APP_STAGE=prod
# S-92: DSN Sentry — build-time, пусто → error-tracking выключен.
ARG VITE_SENTRY_DSN=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
# S-61: CSP_MODE (enforce|report-only) — роль мини-скрипта в docker-entrypoint.d;
# staging-контур ставит CSP_MODE=report-only до закрытия аудита CSP.
COPY docker-entrypoint.d/40-csp.sh /docker-entrypoint.d/40-csp.sh
RUN chmod 0755 /docker-entrypoint.d/40-csp.sh
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
