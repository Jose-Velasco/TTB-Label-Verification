# Pinned base — see deploy/README.md for the image-pinning policy (avoid
# floating tags like python:3.12-slim that silently pick up a new Debian
# release over time).
FROM python:3.12-slim-bookworm

# Install UV — pinned (was ghcr.io/astral-sh/uv:latest; a floating tag here
# would silently change the deployed build toolchain between builds).
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /usr/local/bin/

# libcairo2 — native dependency of cairosvg (app/services/golden_samples.py),
# used at runtime by /api/stress-test/run to rasterize the golden label SVGs.
# Without this, cairosvg.svg2png() raises OSError on first call and the
# endpoint 500s — cairosvg's Python package alone isn't enough, it dlopen()s
# the actual Cairo shared library.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies into the system Python instead of a .venv — current uv
# (unlike the older `uv sync --system` flag this replaced) does this via
# UV_PROJECT_ENVIRONMENT pointed at the system prefix.
ENV UV_PROJECT_ENVIRONMENT=/usr/local

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock* ./

RUN uv sync --frozen --no-dev

# Dedicated non-root user — uvicorn binds an unprivileged port (8000) and the
# app writes nowhere but /tmp (multipart upload spooling), so it never needs
# root. System packages installed above stay root-owned but world-readable,
# same as any other non-root process using base system Python packages.
RUN groupadd --system appuser \
    && useradd --system --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

# Copy application code
COPY --chown=appuser:appuser app/ ./app/

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
