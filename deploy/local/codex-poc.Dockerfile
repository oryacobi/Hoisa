FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.141.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bubblewrap \
        ca-certificates \
        git \
        ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@openai/codex@${CODEX_VERSION}"

WORKDIR /workspace
