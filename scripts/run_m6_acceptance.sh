#!/usr/bin/env bash
set -e
/home/z/.venv/bin/python -c "
import pgserver
s = pgserver.get_server('/home/z/my-project/pgdata', cleanup_mode=None)
s.ensure_pgdata_inited(); s.ensure_postgres_running()
print('pg ready')
" 2>&1 | tail -1

if ! /tmp/redis-stable/src/redis-cli ping > /dev/null 2>&1; then
    mkdir -p /tmp/redis-data
    /tmp/redis-stable/src/redis-server --port 6379 --daemonize yes --dir /tmp/redis-data --logfile /tmp/redis.log --save "" --appendonly no
    sleep 1
fi

cd /home/z/my-project/pamm-platform/backend
unset DATABASE_URL
/home/z/.venv/bin/alembic upgrade head 2>&1 | tail -2
/home/z/.venv/bin/python -m app.seed 2>&1 | tail -2

REDIS_URL="redis://localhost:6379/0" /home/z/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/m6_uv.log 2>&1 &
UVPID=$!
for i in $(seq 1 20); do
  if curl -sS -m 1 http://127.0.0.1:8000/health > /dev/null 2>&1; then break; fi
  sleep 0.5
done
echo "--- version ---"
curl -sS http://127.0.0.1:8000/health; echo

python3 /home/z/my-project/pamm-platform/scripts/m6_acceptance.py
RESULT=$?

kill $UVPID 2>/dev/null || true
wait $UVPID 2>/dev/null || true
exit $RESULT
