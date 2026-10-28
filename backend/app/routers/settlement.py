from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..auth import get_principal, Principal
from ..db import get_db
from ..models import Rollover, SettlementLeaf, SettlementRoot, Subscription, InvestorAccount, RolloverEntry
from ..domain import merkle
from ..schemas import MerkleProofOut

router = APIRouter()

@router.get("/rollovers/{rollover_id}/merkle-root")
def get_root(rollover_id: str, p: Annotated[Principal, Depends(get_principal)],
             db: Session = Depends(get_db)):
    r = db.query(Rollover).filter(Rollover.id == rollover_id).first()
    if not r: raise HTTPException(404, "Rollover not found")
    if not p.is_super_admin and r.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    sr = db.query(SettlementRoot).filter(SettlementRoot.rollover_id == rollover_id).first()
    if not sr: raise HTTPException(404, "No settlement root for rollover")
    return {"rollover_id": rollover_id, "root_hash": sr.root_hash, "leaf_count": sr.leaf_count}

@router.get("/rollovers/{rollover_id}/proofs/{subscription_id}", response_model=MerkleProofOut)
def get_proof(rollover_id: str, subscription_id: str,
              p: Annotated[Principal, Depends(get_principal)],
              db: Session = Depends(get_db)):
    r = db.query(Rollover).filter(Rollover.id == rollover_id).first()
    if not r: raise HTTPException(404, "Rollover not found")
    if not p.is_super_admin and r.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    if p.role == "investor":
        s = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if not s or s.investor_user_id != p.user_id:
            raise HTTPException(403, "Not your subscription")
    sr = db.query(SettlementRoot).filter(SettlementRoot.rollover_id == rollover_id).first()
    if not sr: raise HTTPException(404, "Settlement root not found")
    leaves = db.query(SettlementLeaf).filter(
        SettlementLeaf.rollover_id == rollover_id,
        SettlementLeaf.tenant_id == r.tenant_id,
    ).order_by(SettlementLeaf.subscription_id.asc()).all()
    leaf_hashes = [l.hash for l in leaves]
    idx = next((i for i, l in enumerate(leaves) if l.subscription_id == subscription_id), None)
    if idx is None: raise HTTPException(404, "No leaf for subscription")
    _, levels = merkle.build_tree(leaf_hashes)
    proof = merkle.inclusion_proof(idx, levels)
    leaf = leaves[idx]
    verified = merkle.verify_proof(leaf.hash, proof, sr.root_hash)
    return MerkleProofOut(
        rollover_id=rollover_id, subscription_id=subscription_id,
        leaf_hash=leaf.hash, leaf_blob=leaf.canonical_blob,
        root_hash=sr.root_hash, path=proof, verified=verified,
    )

@router.get("/rollovers/{rollover_id}/statement/{subscription_id}")
def get_statement(rollover_id: str, subscription_id: str,
                  p: Annotated[Principal, Depends(get_principal)],
                  db: Session = Depends(get_db)):
    r = db.query(Rollover).filter(Rollover.id == rollover_id).first()
    if not r: raise HTTPException(404, "Rollover not found")
    if not p.is_super_admin and r.tenant_id != p.tenant_id:
        raise HTTPException(403, "Cross-tenant access denied")
    if p.role == "investor":
        s = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if not s or s.investor_user_id != p.user_id:
            raise HTTPException(403, "Not your subscription")
    e = db.query(RolloverEntry).filter(RolloverEntry.rollover_id == rollover_id,
                                        RolloverEntry.subscription_id == subscription_id).first()
    if not e: raise HTTPException(404, "Entry not found")
    s = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    inv = db.query(InvestorAccount).filter(InvestorAccount.id == s.investor_account_id).first()
    sr = db.query(SettlementRoot).filter(SettlementRoot.rollover_id == rollover_id).first()
    return {
        "statement_id": f"STMT-{rollover_id[:8]}-{subscription_id[:8]}",
        "rollover_id": rollover_id, "subscription_id": subscription_id,
        "investor_login": inv.login if inv else None,
        "period_start": r.period_start.isoformat(), "period_end": r.period_end.isoformat(),
        "method": r.method, "units": str(e.units), "nav_before": str(e.nav_before),
        "nav_after": str(e.nav_after), "pnl_share": str(e.pnl_share),
        "performance_fee": str(e.performance_fee), "units_after": str(e.units_after),
        "merkle_root": sr.root_hash if sr else None,
        "currency": inv.currency if inv else "USD",
        "note": "Generated from actual rollover records. Simulated broker data where applicable.",
    }

@router.get("/audit/verify")
def verify_audit(p: Annotated[Principal, Depends(get_principal)], db: Session = Depends(get_db)):
    from ..domain.events import verify_audit_chain
    if not p.tenant_id: return {"verified": False, "reason": "super_admin has no tenant scope"}
    return {"tenant_id": p.tenant_id, "verified": verify_audit_chain(db, p.tenant_id)}
