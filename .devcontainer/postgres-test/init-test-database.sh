#!/usr/bin/env bash
# Runs on every start of the test database (its data directory is on tmpfs, so
# it is always empty). Creates the role and the database that tests connect to;
# the tests load the schema and the seed themselves, so it is never stale.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v test_password="$FORNADA_TEST_DB_PASSWORD" <<'SQL'
CREATE ROLE fornada_test LOGIN PASSWORD :'test_password';
CREATE DATABASE fornada_test OWNER fornada_test;
SQL
