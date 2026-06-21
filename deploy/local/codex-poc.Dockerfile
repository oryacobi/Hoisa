FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bubblewrap ca-certificates git ripgrep \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @openai/codex@0.141.0

WORKDIR /workspace
