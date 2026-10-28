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

cd /home/z/my-project/pamm-platform/backend
unset DATABASE_URL
/home/z/.venv/bin/alembic upgrade head 2>&1 | tail -2
/home/z/.venv/bin/python -m app.seed 2>&1 | tail -2

# Start uvicorn with USE_FAKEREDIS=1
USE_FAKEREDIS=1 /home/z/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/m5_uv.log 2>&1 &
UVPID=$!
echo "uvicorn pid=$UVPID (USE_FAKEREDIS=1)"
for i in $(seq 1 20); do
  if curl -sS -m 1 http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "ready after ${i} tries"; break
  fi
  sleep 0.5
done
echo "--- version ---"
curl -sS http://127.0.0.1:8000/health; echo

USE_FAKEREDIS=1 python3 /home/z/my-project/pamm-platform/scripts/m5_acceptance.py
RESULT=$?

kill $UVPID 2>/dev/null || true
wait $UVPID 2>/dev/null || true
exit $RESULT
