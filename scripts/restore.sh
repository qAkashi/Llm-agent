#!/bin/bash
set -euo pipefail
# Runs only on an EMPTY PGDATA. Velero's FSB init container restores /backup first.
psql --username=postgres --dbname=app --set=ON_ERROR_STOP=1 \
  --set=reader_password="$APP_PASSWORD" <<'SQL'
CREATE ROLE reader LOGIN PASSWORD :'reader_password';
ALTER ROLE reader SET default_transaction_read_only = on;
GRANT USAGE ON SCHEMA public TO reader;
SQL
if [ -f /backup/app.dump ]; then
  cd /backup
  rmdir /backup/.dump-lock 2>/dev/null || true
  sha256sum --check app.dump.sha256
  pg_restore --username=postgres --dbname=app --no-owner --no-acl \
    --exit-on-error --single-transaction /backup/app.dump
  psql --username=postgres --dbname=app --set=ON_ERROR_STOP=1 \
    -c 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO reader;'
  echo 'RESTORE_IMPORT_COMPLETED'
else
  echo 'INITIAL_EMPTY_DATABASE: seed.sql must be run explicitly by the operator'
fi
