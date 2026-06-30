# Dev container image — Python 3.12 base with Node 20 and UV layered on top.
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bullseye

# Node.js 20 LTS — needed to run the Next.js dev server
# RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
#     && apt-get install -y --no-install-recommends nodejs \
#     && apt-get clean && rm -rf /var/lib/apt/lists/*

# UV — fast Python package manager (same as what the backend Dockerfile uses)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Verify installs — surfaces version mismatches early
RUN python --version && uv --version
