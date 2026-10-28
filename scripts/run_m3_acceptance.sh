#!/usr/bin/env bash
set -e
cd /home/z/my-project/pamm-platform/backend
unset DATABASE_URL

/home/z/.venv/bin/python -c "
import pgserver
s = pgserver.get_server('/home/z/my-project/pgdata', cleanup_mode=None)
s.ensure_pgdata_inited()
s.ensure_postgres_running()
print('postgres pid:', s.get_pid())
" 2>&1 | tail -2

/home/z/.venv/bin/alembic upgrade head 2>&1 | tail -2
/home/z/.venv/bin/python -m app.seed 2>&1 | tail -2

/home/z/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/m3_uvicorn.log 2>&1 &
UVPID=$!
echo "uvicorn pid=$UVPID"
for i in $(seq 1 20); do
  if curl -sS -m 1 http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo "ready after ${i} tries"; break
  fi
  sleep 0.5
done

python3 /home/z/my-project/pamm-platform/scripts/m3_acceptance.py
RESULT=$?

kill $UVPID 2>/dev/null || true
wait $UVPID 2>/dev/null || true
exit $RESULT
