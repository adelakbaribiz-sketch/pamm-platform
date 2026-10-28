#!/usr/bin/env bash
set -e
# Start postgres
/home/z/.venv/bin/python -c "
import pgserver
s = pgserver.get_server('/home/z/my-project/pgdata', cleanup_mode=None)
s.ensure_pgdata_inited()
s.ensure_postgres_running()
print('pg ready')
" 2>&1 | tail -1

# Verify redis is running
REDIS_BIN=/tmp/redis-stable/src/redis-cli
if ! $REDIS_BIN ping > /dev/null 2>&1; then
    echo "Starting redis-server..."
    mkdir -p /tmp/redis-data
    /tmp/redis-stable/src/redis-server --port 6379 --daemonize yes --dir /tmp/redis-data --logfile /tmp/redis.log --save "" --appendonly no
    sleep 1
fi
echo "redis: $($REDIS_BIN ping)"
echo "redis version: $($REDIS_BIN info server | grep redis_version | tr -d '\r')"

cd /home/z/my-project/pamm-platform/backend
unset DATABASE_URL
/home/z/.venv/bin/alembic upgrade head 2>&1 | tail -2
/home/z/.venv/bin/python -m app.seed 2>&1 | tail -2

# Start uvicorn WITHOUT fakeredis — use real Redis
REDIS_URL="redis://localhost:6379/0" /home/z/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/m6_uv.log 2>&1 &
UVPID=$!
echo "uvicorn pid=$UVPID (REDIS_URL=redis://localhost:6379/0)"
for i in $(seq 1 20); do
  if curl -sS -m 1 http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "ready after ${i} tries"; break
  fi
  sleep 0.5
done
echo "--- version ---"
curl -sS http://127.0.0.1:8000/health; echo

REDIS_URL="redis://localhost:6379/0" PYTHONPATH=/home/z/my-project/pamm-platform/backend python3 /home/z/my-project/pamm-platform/scripts/real_redis_e2e.py
RESULT=$?

kill $UVPID 2>/dev/null || true
wait $UVPID 2>/dev/null || true
exit $RESULT
