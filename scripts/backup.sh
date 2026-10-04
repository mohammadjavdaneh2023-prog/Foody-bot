#!/bin/sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_ENCRYPTION_PASSPHRASE:?BACKUP_ENCRYPTION_PASSPHRASE is required}"

output_dir=${1:?usage: backup.sh /secure/output-directory}
mkdir -p "$output_dir"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="$output_dir/foody-$timestamp.dump.enc"
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT HUP INT TERM
umask 077

pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges --file="$temporary"
openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 \
  -pass env:BACKUP_ENCRYPTION_PASSPHRASE -in "$temporary" -out "$output"
echo "$output"
