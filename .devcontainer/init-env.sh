#!/usr/bin/env bash
# Runs on the host before the dev container starts (initializeCommand).
# Creates `.devcontainer/.env` (dev environment secrets, not app settings)
# with random values if it does not exist yet, and adds secrets introduced
# later to an existing file without touching the others.
set -euo pipefail

env_file="$(dirname "$0")/.env"

hex() { openssl rand -hex "$1"; }

# Value of KEY in the env file (last assignment wins, like compose).
env_value() { sed -n "s/^$1=//p" "$env_file" | tail -n 1; }

# HTTP Basic credential for the Collector's Langfuse exporter:
# base64("public_key:secret_key"), on one line (GNU base64 wraps at 76 chars).
langfuse_otlp_auth() { printf '%s:%s' "$1" "$2" | base64 | tr -d '\n'; }

# Append KEY=VALUE to the env file, keeping its last line intact if the file
# does not end with a newline.
append_env() {
  [[ -n "$(tail -c 1 "$env_file")" ]] && echo >> "$env_file"
  echo "$1=$2" >> "$env_file"
  echo "Added $1 to .devcontainer/.env."
}

# Append KEY=VALUE only if KEY has no value yet; never rewrite an existing one.
ensure_secret() { [[ -n "$(env_value "$1")" ]] || append_env "$1" "$2"; }

if [[ ! -f "$env_file" ]]; then
  langfuse_public_key="pk-lf-$(hex 16)"
  langfuse_secret_key="sk-lf-$(hex 16)"
  cat > "$env_file" <<EOF
POSTGRES_PASSWORD=$(hex 24)
FORNADA_DB_PASSWORD=$(hex 24)
POSTGRES_TEST_PASSWORD=$(hex 24)
FORNADA_TEST_DB_PASSWORD=$(hex 24)
LANGFUSE_DB_PASSWORD=$(hex 24)
LANGFUSE_SALT=$(hex 24)
LANGFUSE_ENCRYPTION_KEY=$(hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(hex 32)
LANGFUSE_PUBLIC_KEY=$langfuse_public_key
LANGFUSE_SECRET_KEY=$langfuse_secret_key
LANGFUSE_OTLP_AUTH=$(langfuse_otlp_auth "$langfuse_public_key" "$langfuse_secret_key")
LANGFUSE_ADMIN_EMAIL=admin@fornada.local
LANGFUSE_ADMIN_PASSWORD=$(hex 12)
CLICKHOUSE_PASSWORD=$(hex 24)
VALKEY_PASSWORD=$(hex 24)
MINIO_ROOT_PASSWORD=$(hex 24)
ELASTIC_PASSWORD=$(hex 24)
KIBANA_SYSTEM_PASSWORD=$(hex 24)
KIBANA_ENCRYPTION_KEY=$(hex 32)
ELASTIC_OTEL_PASSWORD=$(hex 24)
PHONE_HASH_SALT=$(hex 32)
EOF
  chmod 600 "$env_file"
  echo "Created .devcontainer/.env with random secrets."
  exit 0
fi

# Files created before the Collector exported to Langfuse: derive the
# credential from the existing keys, so the Langfuse project still matches.
if [[ -z "$(env_value LANGFUSE_OTLP_AUTH)" ]]; then
  langfuse_public_key="$(env_value LANGFUSE_PUBLIC_KEY)"
  langfuse_secret_key="$(env_value LANGFUSE_SECRET_KEY)"
  if [[ -z "$langfuse_public_key" || -z "$langfuse_secret_key" ]]; then
    echo "init-env: LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY missing in $env_file" >&2
    exit 1
  fi
  append_env LANGFUSE_OTLP_AUTH "$(langfuse_otlp_auth "$langfuse_public_key" "$langfuse_secret_key")"
fi

# Random secrets introduced after the file was created.
ensure_secret ELASTIC_PASSWORD "$(hex 24)"
ensure_secret KIBANA_SYSTEM_PASSWORD "$(hex 24)"
ensure_secret KIBANA_ENCRYPTION_KEY "$(hex 32)"
ensure_secret ELASTIC_OTEL_PASSWORD "$(hex 24)"
ensure_secret PHONE_HASH_SALT "$(hex 32)"
ensure_secret POSTGRES_TEST_PASSWORD "$(hex 24)"
ensure_secret FORNADA_TEST_DB_PASSWORD "$(hex 24)"
