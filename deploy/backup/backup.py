#!/usr/bin/env python3
"""
PAMM Platform — database backup script (Python implementation).

Uses SQLAlchemy + psycopg to produce a SQL dump without requiring pg_dump.
This is a fallback for environments where pg_dump isn't installed (e.g.,
container sandboxes). For production, prefer the bash script + pg_dump
(faster, more battle-tested).

Usage:
    DATABASE_URL=... python deploy/backup/backup.py [output_dir]

Produces a .sql file with INSERT statements for all tables in the public schema.
"""
import os, sys, gzip, datetime
from pathlib import Path

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    output_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "./backups")
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_file = output_dir / f"pamm-{ts}.sql.gz"

    try:
        import psycopg
        from urllib.parse import urlparse, parse_qs, unquote
        # Parse the URL to get connection params
        # Support both postgresql://user:pw@host:port/db and postgresql://user:pw@/db?host=/path
        parts = urlparse(db_url.replace("postgresql+psycopg://", "postgresql://"))
        host = parts.hostname or "localhost"
        port = parts.port or 5432
        user = parts.username or "postgres"
        password = parts.password or ""
        dbname = parts.path.lstrip("/") or "postgres"
        # Override host if query string has host= (unix socket)
        if parts.query:
            qs = parse_qs(parts.query)
            if "host" in qs:
                host = qs["host"][0]

        print(f"[{datetime.datetime.utcnow().isoformat()}Z] Starting backup to {out_file}")

        with psycopg.connect(host=host, port=port, user=user, password=password, dbname=dbname) as conn:
            with conn.cursor() as cur:
                # Get all tables in public schema
                cur.execute("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """)
                tables = [r[0] for r in cur.fetchall()]
                print(f"  Found {len(tables)} tables")

                with gzip.open(out_file, "wt") as f:
                    f.write(f"-- PAMM Platform backup\n")
                    f.write(f"-- Generated: {datetime.datetime.utcnow().isoformat()}Z\n")
                    f.write(f"-- Database: {dbname}\n")
                    f.write(f"-- Tables: {len(tables)}\n\n")
                    f.write("SET statement_timeout = 0;\n")
                    f.write("SET lock_timeout = 0;\n")
                    f.write("SET client_encoding = 'UTF8';\n")
                    f.write("SET standard_conforming_strings = on;\n\n")

                    # Disable FK checks during restore
                    f.write("SET session_replication_role = replica;\n\n")

                    # Truncate ALL tables in one statement (avoids CASCADE side-effects)
                    all_tables_quoted = ", ".join(f'"{t}"' for t in tables)
                    f.write(f"TRUNCATE TABLE {all_tables_quoted} RESTART IDENTITY;\n\n")

                    for table in tables:
                        # Get column names + types
                        cur.execute("""
                            SELECT column_name, data_type FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = %s
                            ORDER BY ordinal_position
                        """, (table,))
                        cols = cur.fetchall()
                        col_names = [c[0] for c in cols]
                        col_types = {c[0]: c[1] for c in cols}

                        f.write(f"-- Table: {table}\n")

                        # Get all rows
                        col_list = ", ".join('"' + c + '"' for c in col_names)
                        cur.execute('SELECT ' + col_list + ' FROM "' + table + '"')
                        rows = cur.fetchall()
                        if not rows:
                            f.write(f"-- (no rows)\n\n")
                            continue

                        from psycopg import sql as pgsql
                        from psycopg.types.json import Jsonb, Json

                        for row in rows:
                            # Wrap dict/list values in Jsonb; use sql.Literal for everything else
                            adapted_values = []
                            for v, cname in zip(row, col_names):
                                col_type = col_types.get(cname, "")
                                if v is None:
                                    adapted_values.append(pgsql.NULL)
                                elif isinstance(v, (dict, list)):
                                    # JSON columns: use Jsonb adapter
                                    adapted_values.append(pgsql.Literal(Jsonb(v)))
                                else:
                                    adapted_values.append(pgsql.Literal(v))
                            cols_str = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in col_names)
                            vals = pgsql.SQL(", ").join(adapted_values)
                            stmt = pgsql.SQL("INSERT INTO {} ({}) VALUES ({});").format(
                                pgsql.Identifier(table), cols_str, vals
                            )
                            composed = stmt.as_string(conn)
                            f.write(composed + "\n")
                        f.write("\n")

                    f.write("SET session_replication_role = DEFAULT;\n")
                    f.write(f"-- End of backup ({len(tables)} tables)\n")

        size = out_file.stat().st_size
        print(f"[{datetime.datetime.utcnow().isoformat()}Z] Backup completed: {out_file} ({size} bytes)")

        # Retention: keep last 30 backups
        backups = sorted(output_dir.glob("pamm-*.sql.gz"))
        retention = int(os.environ.get("BACKUP_RETENTION", "30"))
        if len(backups) > retention:
            for old in backups[:-retention]:
                old.unlink()
                print(f"  Deleted old backup: {old.name}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
