# Production deployment

Single Linode host, Docker Compose, nginx as the only publicly exposed
container. Both the Angular frontend and the FastAPI backend are served from
one origin (nginx reverse-proxies `/api/*` to the backend, everything else to
the frontend) — no GitHub Pages, no separate frontend host, no cross-origin
cookie complications.

```
                 ┌───────────────────────────┐
 :80  ──redirect─►                           │
                 │   nginx (public)          │
 :443 ───────────►   deploy/nginx.conf       │
                 │                           │
                 │   /api/*  ──► backend:8000│  (internal only)
                 │   /*      ──► frontend:8080│ (internal only)
                 └───────────────────────────┘
```

- `backend` and `frontend` publish no host ports (`expose` only) — nginx is
  the only container reachable from outside the host.
- `backend` talks to the real OpenAI API only (`VISION_MODEL=openai/gpt-4o-mini`).
  No Ollama service in this compose file — the Linode host has no GPU.
- Auth is a single shared-password cookie (`ttb_auth`, httponly,
  `SameSite=Lax`, `Secure` in prod). Same-origin deployment means this is
  sufficient — there is no cross-site cookie scenario here to design around.

## Prerequisites

- A Linode (or similar) host running Docker + the Compose plugin
  (`docker compose version` should work).
- A DNS **A record** for a subdomain (e.g. `ttb.yourdomain.com`) pointing at
  the host's IP. Let's Encrypt cannot issue a certificate for a bare IP —
  you need a real domain/subdomain.
- `certbot` installed on the host itself (not in Docker):
  ```
  sudo apt update && sudo apt install -y certbot
  ```
  This also installs `certbot.timer`, a systemd timer that runs `certbot
  renew` automatically twice a day — that's the "built-in" renewal this setup
  relies on; you don't write your own cron job for it.

## 1. Configure secrets

```
cp .env.prod.example .env.prod
```

Edit `.env.prod` and fill in:

- `OPENAI_API_KEY` — your real key. **This file is gitignored and must never
  be committed** (confirmed: `.env.prod` is listed in `.gitignore` alongside
  `.env`, `.env.dev`, `.env.local`). It's the only place this key lives on
  the server.
- `APP_ACCESS_KEY` — a strong random password (this *is* the app's auth
  secret, shared by everyone who logs in).
- `FRONTEND_URL` — `https://your-subdomain.example.com` (your real domain).
- `COOKIE_SECURE=true` — must stay `true` in production.

The Angular production build embeds none of this. `frontend/src/environments/environment.prod.ts`
hardcodes `apiBase: '/api'` (a relative, same-origin path) — there is no API
key or secret for the frontend to embed in the first place, since it never
talks to anything but `/api` on its own origin.

Replace the `YOUR_DOMAIN` placeholder in `deploy/nginx.conf` (three
occurrences) with your real subdomain before continuing.

## 2. TLS bootstrap (first time only)

nginx's config references a certificate that doesn't exist yet on a brand
new host, and `ssl_certificate` makes nginx refuse to start if the file is
missing — so the first certificate has to exist *before* the stack's `443`
server block can come up. The standard way around this chicken-and-egg
problem is a throwaway self-signed cert that gets overwritten by the real one
once nginx (and its ACME challenge path) is actually running:

```bash
DOMAIN=your-subdomain.example.com

# Shared paths nginx and certbot both need
sudo mkdir -p /var/www/certbot /etc/letsencrypt/live/$DOMAIN

# 1. Throwaway self-signed cert so nginx has *something* to load at startup
sudo openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
  -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
  -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
  -subj "/CN=$DOMAIN"

# 2. Bring the stack up — nginx starts fine now (dummy cert is present)
docker compose -f docker-compose.prod.yml up -d --build

# 3. Request the REAL certificate via the now-running nginx's webroot —
#    this is the exact command to use, both now and for every future manual
#    check (routine renewal is automatic — see below)
sudo certbot certonly --webroot -w /var/www/certbot \
  -d $DOMAIN --email you@example.com --agree-tos --no-eff-email

# 4. Reload nginx to pick up the real cert — no downtime, no restart needed
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

Using `--webroot` (not `--standalone`) for the *initial* cert matters: certbot
saves whichever authenticator you used the first time and reuses it for every
renewal. If the first cert were issued with `--standalone` (which binds port
80 itself), every later renewal would try to bind port 80 too — and fail,
because the nginx container already holds it permanently. `--webroot` avoids
that entirely: it just drops a file nginx serves, no port binding involved,
so the exact same method works unchanged for both the first issuance and
every automatic renewal after.

**Cert volume mount**: `/etc/letsencrypt` on the host → `/etc/letsencrypt:ro`
in the nginx container (see `docker-compose.prod.yml`). Certbot (on the host)
writes there; nginx only ever reads.

## 3. Renewal (automatic)

`certbot.timer` (installed with the apt package) already runs `certbot renew`
twice daily — nothing to schedule yourself. It only renews when a cert is
within 30 days of expiring, so most runs are no-ops. The one thing to add is
telling nginx to reload after a renewal actually happens, since nginx caches
the certificate in memory until reloaded:

```bash
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null << 'EOF'
#!/bin/sh
docker compose -f /path/to/docker-compose.prod.yml exec nginx nginx -s reload
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
```

(Replace `/path/to/` with wherever this repo actually lives on the host.)
Certbot runs every executable script in `renewal-hooks/deploy/` automatically
after a successful renewal — this is certbot's own supported hook mechanism,
not a separate cron job.

Test the whole renewal path without actually renewing:
```
sudo certbot renew --dry-run
```

## Bringing the stack up / redeploying

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Rebuilds any service whose image is stale and (re)starts everything with
`restart: unless-stopped`, so the stack survives a host reboot.

## Logs

```bash
docker compose -f docker-compose.prod.yml logs -f nginx
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend
```

## Verifying streaming still works in production

Batch verification (`/api/verify-batch`) and the stress-test runner
(`/api/stress-test/run`) both stream NDJSON results as each image finishes —
if nginx's `proxy_buffering off` (see `deploy/nginx.conf`) ever regresses,
results silently collapse into one lump response delivered only at the end
instead of arriving incrementally. To confirm it's actually streaming against
the real deployed stack (not just checking the config exists):

```bash
# Log in first to get the auth cookie
curl -c /tmp/cookies.txt -X POST https://$DOMAIN/api/login \
  -H 'Content-Type: application/json' \
  -d '{"password":"<APP_ACCESS_KEY>"}'

# -N disables curl's own response buffering; timestamp each line as it
# arrives — lines should print several seconds apart, not all at once
curl -N -b /tmp/cookies.txt -X POST https://$DOMAIN/api/stress-test/run \
  -H 'Content-Type: application/json' -d '{"count": 10}' \
  | while IFS= read -r line; do printf '%s  %s\n' "$(date +%T.%3N)" "$line"; done
```

If streaming is intact, timestamps advance between lines (roughly one every
few seconds, matching however long each real vision-model call takes). If it
regressed to buffering, every line prints with the same timestamp, all at
once at the very end. The same check works from a browser's Network tab on
the actual Batch or Stress Test page — response should show data arriving
progressively rather than one payload after a long pause.

## Notes / rationale

- **Resource limits** (`mem_limit`/`cpus` in `docker-compose.prod.yml`) are
  sized for a 4GB/2CPU host: backend 2GB/1.5 CPU (image processing is the
  heaviest thing it does), frontend 256MB/0.5 CPU (static file serving),
  nginx 128MB/0.5 CPU. Total 2.4GB, leaving headroom for the host OS, Docker
  daemon, and host-installed certbot.
- **Non-root containers**: `backend/Dockerfile` and `frontend/Dockerfile`
  both run as a dedicated non-root user (`appuser` / the nginx image's
  built-in `nginx` user respectively) — see the comments in each Dockerfile
  for how each achieves it without needing a privileged port.
- **Pinned base images**: `nginx:1.27-alpine`, `python:3.12-slim-bookworm`,
  `node:22.22-alpine3.24`, and `ghcr.io/astral-sh/uv:0.11.26` — all exact
  tags, not floating ones like `nginx:alpine` or `python:3.12-slim`, so a
  rebuild months from now doesn't silently pick up a different OS/runtime
  patch version. Bump these deliberately, not by accident.
