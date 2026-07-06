# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ─────────────────────────────────────────────
# Pinned — see deploy/README.md for the image-pinning policy (avoid floating
# tags like node:22-alpine that silently pick up new patch/Alpine releases).
FROM node:22.22-alpine3.24 AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# ── Stage 2: production build ──────────────────────────────────────────────────
FROM builder AS prod-build
COPY . .
RUN npm run build

# ── Stage 3: nginx static server ──────────────────────────────────────────────
# Internal-only container (never published to the host — deploy/nginx.conf
# reverse-proxies to it), so it doesn't need a privileged port. This lets the
# whole process, master included, run as the image's built-in unprivileged
# "nginx" user instead of the default root — nginx.conf listens on 8080, not
# 80, to make that possible. (The base image's own /etc/nginx/nginx.conf still
# has a `user nginx;` directive left over from its normal root-master setup;
# with no root to drop from, nginx just logs a harmless startup warning and
# ignores it — not an error.)
FROM nginx:1.27-alpine AS runner
COPY --from=prod-build /app/dist/ttb-label-verification/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN chown -R nginx:nginx /var/cache/nginx /usr/share/nginx/html \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
