#!/usr/bin/env python3
"""
PAMM Platform — database restore script (Python implementation).

Restores a gzipped SQL dump produced by backup.py.
Refuses to restore to a database URL containing 'pamm' (production) unless
--confirm is passed.

Usage:
    DATABASE_URL=... python deploy/backup/restore.py <backup_file.sql.gz> [--confirm]
"""
import os, sys, gzip
from pathlib import Path
from urllib.parse import urlparse, parse_qs

def main():
    if len(sys.argv) < 2:
        print("Usage: restore.py <backup_file.sql.gz> [--confirm]", file=sys.stderr)
        return 2

    backup_file = Path(sys.argv[1])
    confirm = sys.argv[2] if len(sys.argv) > 2 else ""
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    if not backup_file.exists():
        print(f"ERROR: backup file not found: {backup_file}", file=sys.stderr)
        return 2

    if "pamm" in db_url and confirm != "--confirm":
        print("WARNING: restoring to a database URL containing 'pamm' (likely production).")
        print("  This will TRUNCATE and REPOPULATE all tables.")
        print("  Pass --confirm to proceed.")
        return 3

    print(f"[restore] Starting restore from {backup_file}")

    parts = urlparse(db_url.replace("postgresql+psycopg://", "postgresql://"))
    host = parts.hostname or "localhost"
    port = parts.port or 5432
    user = parts.username or "postgres"
    password = parts.password or ""
    dbname = parts.path.lstrip("/") or "postgres"
    if parts.query:
        qs = parse_qs(parts.query)
        if "host" in qs:
            host = qs["host"][0]

    import psycopg
    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as conn:
        # IMPORTANT: do NOT use autocommit. Run the entire restore in a single
        # transaction so that `SET session_replication_role = replica` persists
        # across all statements (disabling FK constraint checks during restore).
        with conn.cursor() as cur:
            with gzip.open(backup_file, "rt") as f:
                sql = f.read()
            # Execute statement by statement (psycopg doesn't support multi-stmt in one execute)
            import re
            # Split on semicolons that are at end of line, but not inside strings
            stmts = re.split(r';\s*\n', sql)
            success = failed = 0
            for stmt in stmts:
                # Strip comment lines (start with --) from the beginning of the statement
                # but keep the actual SQL that follows
                lines = stmt.split("\n")
                sql_lines = [l for l in lines if not l.strip().startswith("--")]
                actual_sql = "\n".join(sql_lines).strip()
                if not actual_sql:
                    continue
                try:
                    cur.execute(actual_sql)
                    success += 1
                except Exception as e:
                    failed += 1
                    if failed <= 5:
                        print(f"  WARN: {str(e)[:120]}")
            conn.commit()
            print(f"[restore] {success} statements succeeded, {failed} failed")

    print(f"[restore] Completed. Verifying table count...")
    with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            count = cur.fetchone()[0]
    print(f"[restore] Tables in 'public' schema: {count}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
