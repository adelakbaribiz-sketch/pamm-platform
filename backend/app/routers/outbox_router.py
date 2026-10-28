"""Outbox router: drain + stats."""
from typing import Annotated
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal, require_roles
from ..db import get_db, SessionLocal
from ..domain.outbox import drain as drain_fn, stats as stats_fn
from ..domain.outbox_worker import OutboxWorker

router = APIRouter()

@router.post("/outbox/drain")
def drain(p: Annotated[Principal, Depends(require_roles("broker_admin", "super_admin"))],
          db: Session = Depends(get_db), limit: int = 100):
    tid = None if p.is_super_admin else p.tenant_id
    # Use the OutboxWorker for Redis Streams support with DB fallback
    worker = OutboxWorker(SessionLocal, redis_url=None)  # uses settings.redis_url
    return worker.drain_pending(limit=limit, tenant_id=tid)

@router.get("/outbox/stats")
def stats(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    tid = None if p.is_super_admin else p.tenant_id
    return stats_fn(db, tenant_id=tid)

