# Dev container image — Python 3.12 base with Node 20 and UV layered on top.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# UV — fast Python package manager (same as what the backend Dockerfile uses)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# libcairo2 — native dependency of cairosvg (used by the backend eval test suite
# to rasterize sample label SVGs to PNG before handing them to Pillow/the vision model)
RUN apt-get update || true \
    && apt-get install -y --no-install-recommends libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Verify installs — surfaces version mismatches early
RUN python --version && uv --version
