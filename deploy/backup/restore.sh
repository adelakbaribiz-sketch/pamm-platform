#!/usr/bin/env bash
# PAMM Platform — database restore script
# Usage: ./deploy/backup/restore.sh <backup_file.sql.gz>
#
# Restores a gzipped SQL dump. Will refuse to restore to a database
# named 'pamm' in production unless --confirm is passed.

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup_file.sql.gz> [--confirm]" >&2
    exit 2
fi

BACKUP_FILE="$1"
CONFIRM="${2:-}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: backup file not found: ${BACKUP_FILE}" >&2
    exit 2
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL environment variable not set" >&2
    exit 2
fi

# Safety check
if [[ "${DATABASE_URL}" == *"pamm"* ]] && [ "${CONFIRM}" != "--confirm" ]; then
    echo "WARNING: You are about to restore to a database that contains 'pamm' in its URL."
    echo "  This will DROP and RECREATE all tables."
    echo "  Pass --confirm to proceed."
    exit 3
fi

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting restore from ${BACKUP_FILE}"

# Extract PG connection info
PG_HOST=$(echo "${DATABASE_URL}" | sed -nE 's|.*@([^:/]+).*|\1|p')
PG_PORT=$(echo "${DATABASE_URL}" | sed -nE 's|.*:([0-9]+)/.*|\1|p' || echo "5432")
PG_USER=$(echo "${DATABASE_URL}" | sed -nE 's|.*://([^:]+):.*|\1|p')
PG_DB=$(echo "${DATABASE_URL}" | sed -nE 's|.*/([^?]+).*|\1|p')
PG_PASSWORD=$(echo "${DATABASE_URL}" | sed -nE 's|.*://[^:]+:([^@]+)@.*|\1|p')

export PGPASSWORD="${PG_PASSWORD}"

echo "  Host: ${PG_HOST}:${PG_PORT}"
echo "  User: ${PG_USER}"
echo "  DB:   ${PG_DB}"

# Restore
gunzip -c "${BACKUP_FILE}" | psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -v ON_ERROR_STOP=1

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Restore completed."

# Verify by counting core tables
TABLE_COUNT=$(psql -h "${PG_HOST}" -p "${PG_PORT}" -U "${PG_USER}" -d "${PG_DB}" -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';")
echo "  Tables in 'public' schema: ${TABLE_COUNT}"

exit 0
