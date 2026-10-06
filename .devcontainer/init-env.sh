#!/usr/bin/env bash
# Runs on the host before the dev container starts (initializeCommand).
# Creates `.devcontainer/.env` (dev environment secrets, not app settings)
# with random values if it does not exist yet.
set -euo pipefail

env_file="$(dirname "$0")/.env"
[[ -f "$env_file" ]] && exit 0

hex() { openssl rand -hex "$1"; }

cat > "$env_file" <<EOF
POSTGRES_PASSWORD=$(hex 24)
FORNADA_DB_PASSWORD=$(hex 24)
LANGFUSE_DB_PASSWORD=$(hex 24)
LANGFUSE_SALT=$(hex 24)
LANGFUSE_ENCRYPTION_KEY=$(hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(hex 32)
LANGFUSE_PUBLIC_KEY=pk-lf-$(hex 16)
LANGFUSE_SECRET_KEY=sk-lf-$(hex 16)
LANGFUSE_ADMIN_EMAIL=admin@fornada.local
LANGFUSE_ADMIN_PASSWORD=$(hex 12)
CLICKHOUSE_PASSWORD=$(hex 24)
VALKEY_PASSWORD=$(hex 24)
MINIO_ROOT_PASSWORD=$(hex 24)

# Optional, fill in by hand
CONTEXT7_API_KEY=
EOF
chmod 600 "$env_file"
echo "Created .devcontainer/.env with random secrets."
