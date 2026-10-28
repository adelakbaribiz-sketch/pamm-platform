"""Event-sourced ledger + transactional outbox + hash-chained audit log."""
import uuid, json, hashlib
from sqlalchemy.orm import Session
from ..models import Event, Outbox, AuditLog

def record_event(db, tenant_id, type_, payload, subject_type=None, subject_id=None,
                 causation_id=None, correlation_id=None, schema_version=1):
    ev = Event(tenant_id=tenant_id, event_id=str(uuid.uuid4()), type=type_,
               subject_type=subject_type, subject_id=subject_id, payload=payload,
               schema_version=schema_version, causation_id=causation_id, correlation_id=correlation_id)
    db.add(ev); db.flush()
    db.add(Outbox(tenant_id=tenant_id, event_id=ev.event_id, status="pending"))
    db.flush()
    return ev

def _canonical_audit(row_dict):
    return json.dumps(row_dict, sort_keys=True, default=str)

def append_audit(db, tenant_id, actor_id, action, resource_type, resource_id,
                 before=None, after=None, reason=None):
    last = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id.desc()).first()
    prev_hash = last.hash if last else "GENESIS"
    canonical = _canonical_audit({
        "tenant_id": tenant_id, "actor_id": actor_id, "action": action,
        "resource_type": resource_type, "resource_id": resource_id,
        "before": before, "after": after, "reason": reason, "prev_hash": prev_hash,
    })
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    entry = AuditLog(tenant_id=tenant_id, actor_id=actor_id, action=action,
                     resource_type=resource_type, resource_id=resource_id,
                     before=before, after=after, reason=reason,
                     prev_hash=prev_hash, hash=h)
    db.add(entry); db.flush()
    return entry

def verify_audit_chain(db, tenant_id):
    rows = db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).order_by(AuditLog.id.asc()).all()
    prev = "GENESIS"
    for row in rows:
        if row.prev_hash != prev: return False
        canonical = _canonical_audit({
            "tenant_id": row.tenant_id, "actor_id": row.actor_id, "action": row.action,
            "resource_type": row.resource_type, "resource_id": row.resource_id,
            "before": row.before, "after": row.after, "reason": row.reason, "prev_hash": row.prev_hash,
        })
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if h != row.hash: return False
        prev = row.hash
    return True
