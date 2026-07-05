FROM python:3.12-slim

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

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

# Copy application code
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
