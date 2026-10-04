#!/bin/sh
set -eu

: "${DATABASE_URL:?DATABASE_URL must point to a new, empty restore database}"
: "${BACKUP_ENCRYPTION_PASSPHRASE:?BACKUP_ENCRYPTION_PASSPHRASE is required}"
backup=${1:?usage: restore.sh path/to/foody.dump.enc}
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT HUP INT TERM
umask 077

existing=$(psql "$DATABASE_URL" --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align \
  --command="SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
if [ "$existing" -ne 0 ]; then
  echo "Refusing to restore into a non-empty public schema" >&2
  exit 1
fi

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass env:BACKUP_ENCRYPTION_PASSPHRASE -in "$backup" -out "$temporary"
pg_restore --dbname="$DATABASE_URL" --no-owner --no-privileges --exit-on-error \
  --single-transaction "$temporary"
psql "$DATABASE_URL" --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only \
  --command="SELECT count(*) FROM schema_migrations WHERE to_regclass('public.profiles') IS NOT NULL;"
echo "Restore completed and schema_migrations is readable"
