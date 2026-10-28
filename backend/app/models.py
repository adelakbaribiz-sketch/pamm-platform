import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, Boolean, DateTime, Text, JSON, ForeignKey, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def new_id() -> str: return str(uuid.uuid4())

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str | None] = mapped_column(String, ForeignKey("tenants.id"), nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Broker(Base):
    __tablename__ = "brokers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    legal_entity: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class TradingServer(Base):
    __tablename__ = "trading_servers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    broker_id: Mapped[str] = mapped_column(String, ForeignKey("brokers.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    adapter_type: Mapped[str] = mapped_column(String, nullable=False)
    connection_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="active")

class MasterAccount(Base):
    __tablename__ = "master_accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    broker_id: Mapped[str] = mapped_column(String, ForeignKey("brokers.id"), nullable=False)
    server_id: Mapped[str] = mapped_column(String, ForeignKey("trading_servers.id"), nullable=False)
    login: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    base_nav: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("100"))
    total_units: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=Decimal("0"))
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    hwm: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    performance_fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.2"))
    management_fee_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))
    allocation_method: Mapped[str] = mapped_column(String, default="euro_days")
    nav_at_period_start: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("100"))
    manager_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, ForeignKey("master_accounts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String, default="pamm")  # pamm|mam|copy
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class InvestorAccount(Base):
    __tablename__ = "investor_accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    broker_id: Mapped[str] = mapped_column(String, ForeignKey("brokers.id"), nullable=False)
    login: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    owner_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, ForeignKey("master_accounts.id"), nullable=False)
    investor_account_id: Mapped[str] = mapped_column(String, ForeignKey("investor_accounts.id"), nullable=False)
    investor_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    units: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=Decimal("0"))
    contributed_capital: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    start_capital: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    end_capital: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    euro_days: Mapped[Decimal] = mapped_column(Numeric(28, 8), default=Decimal("0"))
    hwm: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String, default="active")
    subscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    detached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Rollover(Base):
    __tablename__ = "rollovers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, ForeignKey("master_accounts.id"), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    master_equity_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    master_equity_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    master_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    total_units: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    nav_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    nav_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    total_performance_fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String, default="completed")
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True)
    created_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    entries: Mapped[list["RolloverEntry"]] = relationship(back_populates="rollover", cascade="all, delete-orphan")

class RolloverEntry(Base):
    __tablename__ = "rollover_entries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    rollover_id: Mapped[str] = mapped_column(String, ForeignKey("rollovers.id"), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String, ForeignKey("subscriptions.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    units: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    start_capital: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    end_capital: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    euro_days: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    pnl_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    performance_fee: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    nav_before: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    nav_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    units_after: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    rollover: Mapped["Rollover"] = relationship(back_populates="entries")

class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, default=new_id)
    type: Mapped[str] = mapped_column(String, nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String)
    subject_id: Mapped[str | None] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    causation_id: Mapped[str | None] = mapped_column(String)
    correlation_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    # NOTE: deliberately no FK to events.event_id — outbox rows may persist as
    # dead-letter records after the event row has been archived.
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String)
    resource_id: Mapped[str | None] = mapped_column(String)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[str | None] = mapped_column(String)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class RiskRule(Base):
    __tablename__ = "risk_rules"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    master_account_id: Mapped[str | None] = mapped_column(String, ForeignKey("master_accounts.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class RiskRejection(Base):
    __tablename__ = "risk_rejections"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    master_account_id: Mapped[str | None] = mapped_column(String)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    reason_details: Mapped[dict | None] = mapped_column(JSON)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class SettlementLeaf(Base):
    __tablename__ = "settlement_leaves"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    rollover_id: Mapped[str] = mapped_column(String, ForeignKey("rollovers.id"), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String, nullable=False)
    canonical_blob: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class SettlementRoot(Base):
    __tablename__ = "settlement_roots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    rollover_id: Mapped[str] = mapped_column(String, ForeignKey("rollovers.id"), unique=True, nullable=False)
    root_hash: Mapped[str] = mapped_column(String, nullable=False)
    leaf_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

# ---------------- M2: MAM ----------------

class MamChildOrder(Base):
    __tablename__ = "mam_child_orders"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    master_order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    master_account_id: Mapped[str] = mapped_column(String, ForeignKey("master_accounts.id"), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String, ForeignKey("subscriptions.id"), nullable=False)
    investor_account_id: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)
    requested_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    allocated_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    residual_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    status: Mapped[str] = mapped_column(String, default="pending")
    filled_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    reject_reason: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

# ---------------- M2: Copy trading ----------------

class CopySubscription(Base):
    __tablename__ = "copy_subscriptions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String, ForeignKey("strategies.id"), nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, ForeignKey("master_accounts.id"), nullable=False)
    follower_account_id: Mapped[str] = mapped_column(String, ForeignKey("investor_accounts.id"), nullable=False)
    follower_user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String, default="active")  # active|paused|detached
    max_lots_per_trade: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    excluded_symbols: Mapped[list] = mapped_column(JSON, default=list)
    lot_multiplier: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("1"))
    subscribed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class CopyTrade(Base):
    __tablename__ = "copy_trades"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String, nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[str] = mapped_column(String, nullable=False)  # buy|sell|close
    master_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    master_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    status: Mapped[str] = mapped_column(String, default="open")  # open|filled|rejected|cancelled
    causation_id: Mapped[str | None] = mapped_column(String, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class CopyFollowerTrade(Base):
    __tablename__ = "copy_follower_trades"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    copy_trade_id: Mapped[str] = mapped_column(String, ForeignKey("copy_trades.id"), nullable=False, index=True)
    copy_subscription_id: Mapped[str] = mapped_column(String, ForeignKey("copy_subscriptions.id"), nullable=False)
    follower_account_id: Mapped[str] = mapped_column(String, nullable=False)
    requested_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    allocated_lots: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|filled|rejected|skipped
    reject_reason: Mapped[str | None] = mapped_column(String)
    server_side_latency_ms: Mapped[int | None] = mapped_column(Integer)
    broker_latency_ms: Mapped[int | None] = mapped_column(Integer)
    slippage_bps: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

# ---------------- M2: Settlement saga (P-3) ----------------

class SettlementSaga(Base):
    __tablename__ = "settlement_sagas"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    saga_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # rollover|mam_batch|copy_close_batch
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|completed|compensating|failed|abandoned
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    completed_steps: Mapped[list] = mapped_column(JSON, default=list)
    failed_step: Mapped[str | None] = mapped_column(String)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    compensation_log: Mapped[list] = mapped_column(JSON, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String, index=True)
    created_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class SagaStep(Base):
    __tablename__ = "saga_steps"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    saga_id: Mapped[str] = mapped_column(String, ForeignKey("settlement_sagas.saga_id"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String, nullable=False)
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|completed|failed|compensated|skipped
    request: Mapped[dict | None] = mapped_column(JSON)
    response: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    is_reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    compensation_action: Mapped[str | None] = mapped_column(String)  # reverse|remediate|manual
    compensation_payload: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

# ---------------- M3: P-1 Constrained Adaptive Allocation ----------------

class AllocationProblem(Base):
    __tablename__ = "allocation_problems"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    objective: Mapped[str] = mapped_column(String, nullable=False)
    investor_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    constraints: Mapped[dict] = mapped_column(JSON, nullable=False)
    solver_status: Mapped[str] = mapped_column(String, default="pending")
    solution: Mapped[dict | None] = mapped_column(JSON)
    objective_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    infeasibility_reason: Mapped[str | None] = mapped_column(Text)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_emitted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class AllocationAlert(Base):
    __tablename__ = "allocation_alerts"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    allocation_problem_id: Mapped[str] = mapped_column(String, ForeignKey("allocation_problems.id"), nullable=False)
    master_account_id: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

# ---------------- M3: P-2 Shadow Latency & Slippage Prediction ----------------

class ExecutionProfile(Base):
    __tablename__ = "execution_profiles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String)
    total_observations: Mapped[int] = mapped_column(Integer, default=0)
    latency_mean_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    latency_std_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    latency_p50_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    latency_p95_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    latency_p99_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    slippage_mean_bps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    slippage_std_bps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

class LatencyPrediction(Base):
    __tablename__ = "latency_predictions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String)
    order_size: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    features: Mapped[dict | None] = mapped_column(JSON)
    predicted_latency_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    predicted_lower_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    predicted_upper_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    predicted_slippage_bps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    actual_latency_ms: Mapped[int | None] = mapped_column(Integer)
    actual_slippage_bps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    residual_latency: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    residual_slippage: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    model_version: Mapped[str] = mapped_column(String, default="v1-linear")
    throttle_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class LatencyObservation(Base):
    __tablename__ = "latency_observations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    destination: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String)
    order_size: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    slippage_bps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    prediction_id: Mapped[str | None] = mapped_column(String, ForeignKey("latency_predictions.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
