# Versions are pinned exactly; Dependabot (.github/dependabot.yml) opens PRs to bump them.
FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

FROM mcr.microsoft.com/devcontainers/base:2.2.1-trixie

ARG TZ=America/Sao_Paulo
ENV TZ=${TZ}

# PostgreSQL client from the PGDG repository, so psql matches the latest server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-common \
    && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        jq \
        ripgrep \
        fd-find \
        fzf \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# uv and uvx. Python itself is managed by uv.
COPY --from=uv /uv /uvx /usr/local/bin/

# Claude Code policy for this container only: start in bypassPermissions mode.
COPY managed-settings.json /etc/claude-code/managed-settings.json

# Mount points for named volumes. Creating them here makes new volumes
# inherit vscode ownership.
RUN mkdir -p /commandhistory /home/vscode/.claude /home/vscode/.cache/uv /home/vscode/.config/gh \
    && chown -R vscode:vscode /commandhistory /home/vscode/.claude /home/vscode/.cache /home/vscode/.config

USER vscode

ENV UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_COMPILE_BYTECODE=1

# Latest stable Python, managed by uv.
RUN uv python install

# Persist shell history across rebuilds.
RUN echo 'export HISTFILE=/commandhistory/.zsh_history' >> /home/vscode/.zshrc \
    && echo 'export HISTFILE=/commandhistory/.bash_history' >> /home/vscode/.bashrc
