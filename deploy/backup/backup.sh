#!/usr/bin/env bash
# PAMM Platform — database backup script
# Usage: ./deploy/backup/backup.sh [output_dir]
#
# Creates a gzipped SQL dump of the pamm database. The dump is in
# plain SQL format (not custom), so it can be restored via psql.
# Includes pre-flight checks and exit codes per Unix convention.

set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
TIMESTAMP=$(date -u +%Y%m%d-%H%M%S)
FILENAME="${OUTPUT_DIR}/pamm-${TIMESTAMP}.sql.gz"

mkdir -p "${OUTPUT_DIR}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting backup to ${FILENAME}"

# Check env vars
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL environment variable not set" >&2
    echo "Example: export DATABASE_URL='postgresql+psycopg://pamm:pw@host:5432/pamm'" >&2
    exit 2
fi

# Extract PG connection info from DATABASE_URL
PG_HOST=$(echo "${DATABASE_URL}" | sed -nE 's|.*@([^:/]+).*|\1|p')
PG_PORT=$(echo "${DATABASE_URL}" | sed -nE 's|.*:([0-9]+)/.*|\1|p' || echo "5432")
PG_USER=$(echo "${DATABASE_URL}" | sed -nE 's|.*://([^:]+):.*|\1|p')
PG_DB=$(echo "${DATABASE_URL}" | sed -nE 's|.*/([^?]+).*|\1|p')
PG_PASSWORD=$(echo "${DATABASE_URL}" | sed -nE 's|.*://[^:]+:([^@]+)@.*|\1|p')

export PGPASSWORD="${PG_PASSWORD}"

echo "  Host: ${PG_HOST}:${PG_PORT}"
echo "  User: ${PG_USER}"
echo "  DB:   ${PG_DB}"

# Run pg_dump
pg_dump -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" \
    --no-owner --no-privileges --clean --if-exists \
    | gzip > "${FILENAME}"

SIZE=$(du -h "${FILENAME}" | cut -f1)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Backup completed: ${FILENAME} (${SIZE})"

# Verify the backup is non-empty
if [ ! -s "${FILENAME}" ]; then
    echo "ERROR: backup file is empty — pg_dump likely failed" >&2
    exit 1
fi

# Retention: delete backups older than 30 days
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
echo "  Cleaning up backups older than ${RETENTION_DAYS} days"
find "${OUTPUT_DIR}" -name "pamm-*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "Done."
exit 0
