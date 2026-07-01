# syntax=docker/dockerfile:1

# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# ── Stage 2: production build ──────────────────────────────────────────────────
FROM builder AS prod-build
COPY . .
RUN npm run build

# ── Stage 3: nginx static server ──────────────────────────────────────────────
FROM nginx:1.27-alpine AS runner
COPY --from=prod-build /app/dist/ttb-label-verification/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
