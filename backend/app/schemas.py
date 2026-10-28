from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: str | None
    user_id: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class RefreshIn(BaseModel):
    refresh_token: str

class BrokerCreate(BaseModel):
    name: str
    legal_entity: str | None = None

class MasterCreate(BaseModel):
    broker_id: str
    server_id: str | None = None
    login: str
    currency: str = "USD"
    base_nav: Decimal = Decimal("100")
    performance_fee_rate: Decimal = Decimal("0.2")
    management_fee_rate: Decimal = Decimal("0")
    allocation_method: str = "euro_days"

class StrategyCreate(BaseModel):
    master_account_id: str
    name: str
    description: str | None = None
    kind: str = "pamm"  # pamm|mam|copy

class InvestorCreate(BaseModel):
    broker_id: str
    login: str
    currency: str = "USD"

class SubscribeIn(BaseModel):
    strategy_id: str
    investor_account_id: str
    capital: Decimal = Field(gt=0)

class RolloverIn(BaseModel):
    master_account_id: str
    method: str | None = None
    idempotency_key: str
    period_days: int = 1

class RolloverEntryOut(BaseModel):
    subscription_id: str
    investor_login: str | None = None
    units: Decimal
    start_capital: Decimal
    end_capital: Decimal
    euro_days: Decimal
    pnl_share: Decimal
    performance_fee: Decimal
    nav_before: Decimal
    nav_after: Decimal
    units_after: Decimal

class RolloverOut(BaseModel):
    id: str
    master_account_id: str
    method: str
    period_start: datetime
    period_end: datetime
    master_equity_before: Decimal | None
    master_equity_after: Decimal | None
    master_pnl: Decimal | None
    nav_before: Decimal | None
    nav_after: Decimal | None
    total_units: Decimal | None
    total_performance_fee: Decimal
    status: str
    idempotency_key: str | None
    entries: list[RolloverEntryOut]

class MerkleProofOut(BaseModel):
    rollover_id: str
    subscription_id: str
    leaf_hash: str
    leaf_blob: str
    root_hash: str
    path: list[dict]
    verified: bool

# -------- M2: MAM --------
class MamInvestorIn(BaseModel):
    subscription_id: str
    investor_account_id: str
    equity: Decimal | None = None
    balance: Decimal | None = None
    percentage: Decimal | None = None
    lot_multiplier: Decimal = Decimal("1")

class MamSplitIn(BaseModel):
    master_account_id: str
    symbol: str
    side: str  # buy|sell
    master_lots: Decimal
    method: str = "equity_ratio"  # equity_ratio|balance_ratio|fixed_lot_mult|percentage
    lot_step: Decimal = Decimal("0.01")
    idempotency_key: str
    price: Decimal | None = None
    investors: list[MamInvestorIn]

class MamChildOut(BaseModel):
    subscription_id: str
    investor_account_id: str
    requested_lots: Decimal
    allocated_lots: Decimal
    residual_lots: Decimal
    status: str
    fill_price: Decimal | None
    reject_reason: str | None

class MamSplitOut(BaseModel):
    master_order_id: str
    children: list[MamChildOut]
    reconciled: bool
    saga_id: str

# -------- M2: Copy --------
class CopySubscribeIn(BaseModel):
    strategy_id: str
    follower_account_id: str
    max_lots_per_trade: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    excluded_symbols: list[str] = Field(default_factory=list)
    lot_multiplier: Decimal = Decimal("1")

class CopyTradeIn(BaseModel):
    strategy_id: str
    master_account_id: str
    symbol: str
    side: str  # buy|sell|close
    master_lots: Decimal
    master_price: Decimal | None = None
    idempotency_key: str

class CopyControlIn(BaseModel):
    copy_subscription_id: str
    action: str  # pause|resume|detach
    close_positions: bool = False

# -------- M2: Saga --------
class SagaCreateIn(BaseModel):
    kind: str  # rollover|mam_batch|copy_close_batch
    steps: list[dict]
    payload: dict
    idempotency_key: str | None = None

class SagaRecoverIn(BaseModel):
    saga_id: str
