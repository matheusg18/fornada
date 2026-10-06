#!/usr/bin/env bash
# Runs inside the container once, after it is created (postCreateCommand).
set -euo pipefail

# Named volumes mounted inside the bind-mounted workspace start root-owned.
sudo chown vscode:vscode /workspaces/fornada/.venv

# Create the virtualenv first, so the interpreter set in devcontainer.json
# exists as early as possible, even before there is a pyproject.toml.
uv venv --allow-existing

# Trust GitHub's SSH host keys, fetched over HTTPS from GitHub's API.
mkdir -p ~/.ssh && chmod 700 ~/.ssh
curl -fsSL https://api.github.com/meta \
  | jq -r '.ssh_keys[] | "github.com " + .' > ~/.ssh/known_hosts

# Browser for the Playwright MCP, which uses the Chrome channel by default.
sudo env "PATH=$PATH" npx -y playwright@latest install --with-deps chrome

# Python dependencies, once the project has a pyproject.toml.
if [[ -f pyproject.toml ]]; then
  uv sync
fi
