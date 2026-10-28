"""Backup/restore script tests."""
import os, sys, gzip, shutil, tempfile
from pathlib import Path

# Add the deploy/backup dir to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deploy" / "backup"))


def test_backup_creates_valid_sql_dump():
    """The backup.py script produces a non-empty gzipped SQL file with expected header."""
    import subprocess
    backup_dir = tempfile.mkdtemp()
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg://pamm:pamm_dev_pw@/pamm?host=/home/z/my-project/pgdata"}
    result = subprocess.run(
        [sys.executable, "/home/z/my-project/pamm-platform/deploy/backup/backup.py", backup_dir],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"backup.py failed: {result.stderr}"
    backups = list(Path(backup_dir).glob("pamm-*.sql.gz"))
    assert len(backups) == 1
    assert backups[0].stat().st_size > 100  # non-empty
    # Verify the dump contains expected header
    with gzip.open(backups[0], "rt") as f:
        content = f.read()
    assert "PAMM Platform backup" in content
    assert "Tables:" in content
    # The pamm DB has rollovers from prior test runs, so INSERT statements should be present
    assert "INSERT INTO" in content, "expected INSERT statements from pamm DB"
    shutil.rmtree(backup_dir)


def test_backup_restore_roundtrip():
    """Backup from pamm, restore to pamm_restore_test, verify data matches."""
    import subprocess
    # Backup source
    backup_dir = tempfile.mkdtemp()
    env = {**os.environ, "DATABASE_URL":
            "postgresql+psycopg://pamm:pamm_dev_pw@/pamm?host=/home/z/my-project/pgdata"}
    r = subprocess.run(
        [sys.executable, "/home/z/my-project/pamm-platform/deploy/backup/backup.py", backup_dir],
        env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    backups = list(Path(backup_dir).glob("pamm-*.sql.gz"))
    assert len(backups) == 1

    # Truncate restore target
    import psycopg
    with psycopg.connect(host="/home/z/my-project/pgdata", user="pamm",
                          password="pamm_dev_pw", dbname="pamm_restore_test") as c:
        c.autocommit = True
        with c.cursor() as cur:
            cur.execute("SET session_replication_role = replica;")
            cur.execute("""
                TRUNCATE tenants, users, brokers, trading_servers, master_accounts,
                         strategies, investor_accounts, subscriptions, rollovers,
                         rollover_entries, events, outbox, audit_log, risk_rules,
                         risk_rejections, settlement_leaves, settlement_roots,
                         mam_child_orders, copy_subscriptions, copy_trades,
                         copy_follower_trades, settlement_sagas, saga_steps,
                         allocation_problems, allocation_alerts, execution_profiles,
                         latency_predictions, latency_observations, alembic_version
                CASCADE
            """)
            cur.execute("SET session_replication_role = DEFAULT;")

    # Restore
    env_restore = {**os.environ, "DATABASE_URL":
            "postgresql+psycopg://pamm:pamm_dev_pw@/pamm_restore_test?host=/home/z/my-project/pgdata"}
    r = subprocess.run(
        [sys.executable, "/home/z/my-project/pamm-platform/deploy/backup/restore.py",
         str(backups[0]), "--confirm"],
        env=env_restore, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "statements succeeded" in r.stdout

    # Verify counts match
    def count(dbname, table):
        with psycopg.connect(host="/home/z/my-project/pgdata", user="pamm",
                              password="pamm_dev_pw", dbname=dbname) as c:
            with c.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {table}")
                return cur.fetchone()[0]

    for table in ["tenants", "users", "risk_rules", "rollovers"]:
        source_count = count("pamm", table)
        restored_count = count("pamm_restore_test", table)
        assert restored_count == source_count, f"{table}: source={source_count}, restored={restored_count}"

    shutil.rmtree(backup_dir)
