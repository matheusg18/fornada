#!/usr/bin/env bash
# Runs once, on the first start of an empty data volume.
# Creates one role and one database for the app and one for Langfuse.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v fornada_password="$FORNADA_DB_PASSWORD" \
  -v langfuse_password="$LANGFUSE_DB_PASSWORD" <<'SQL'
CREATE ROLE fornada LOGIN PASSWORD :'fornada_password';
CREATE DATABASE fornada OWNER fornada;

CREATE ROLE langfuse LOGIN PASSWORD :'langfuse_password';
CREATE DATABASE langfuse OWNER langfuse;
SQL
