#!/bin/bash
set -euo pipefail
if [ "$(id -u)" = 0 ]; then exec gosu postgres /bin/bash "$0"; fi
umask 077
export PGPASSWORD="$POSTGRES_PASSWORD"
mkdir /backup/.dump-lock
trap 'rm -f /backup/app.dump.tmp; rmdir /backup/.dump-lock' ERR
pg_dump --host=127.0.0.1 --username=postgres --dbname=app \
  --format=custom --no-owner --no-acl --file=/backup/app.dump.tmp
pg_restore --list /backup/app.dump.tmp >/dev/null
mv /backup/app.dump.tmp /backup/app.dump
cd /backup
sha256sum app.dump > app.dump.sha256
stat -c '%s' app.dump > dump-bytes.txt
date -u +'%Y-%m-%dT%H:%M:%SZ' > dump-created-utc.txt
sync
