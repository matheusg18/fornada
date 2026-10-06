#!/usr/bin/env bash
# Runs once, on the first start of an empty data volume.
# Creates one role and one database for the app and one for Langfuse, then
# loads the app schema and seed into the fornada database.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v fornada_password="$FORNADA_DB_PASSWORD" \
  -v langfuse_password="$LANGFUSE_DB_PASSWORD" <<'SQL'
CREATE ROLE fornada LOGIN PASSWORD :'fornada_password';
CREATE DATABASE fornada OWNER fornada;

CREATE ROLE langfuse LOGIN PASSWORD :'langfuse_password';
CREATE DATABASE langfuse OWNER langfuse;
SQL

# One session: SET ROLE makes fornada the owner of every table (this script
# runs as the superuser). Files come from the .devcontainer/db mount in compose.yaml.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname fornada \
  -c 'SET ROLE fornada' \
  -f /fornada-db/schema.sql \
  -f /fornada-db/seed.sql
