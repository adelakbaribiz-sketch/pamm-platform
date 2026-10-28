"""initial schema m1+m2"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # NOTE: pgcrypto intentionally omitted — UUIDs generated in Python.
    # ---------- M1 core ----------
    op.create_table(
        "tenants",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("slug", sa.String, unique=True, nullable=False),
        sa.Column("status", sa.String, default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("email", sa.String, unique=True, nullable=False),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("status", sa.String, default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_tenant", "users", ["tenant_id"])
    op.create_table(
        "brokers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("legal_entity", sa.String),
        sa.Column("status", sa.String, default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "trading_servers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("broker_id", sa.String, sa.ForeignKey("brokers.id"), nullable=False),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("adapter_type", sa.String, nullable=False),
        sa.Column("connection_config", sa.JSON, default={}),
        sa.Column("status", sa.String, default="active"),
    )
    op.create_table(
        "master_accounts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("broker_id", sa.String, sa.ForeignKey("brokers.id"), nullable=False),
        sa.Column("server_id", sa.String, sa.ForeignKey("trading_servers.id"), nullable=False),
        sa.Column("login", sa.String, nullable=False),
        sa.Column("currency", sa.String(3), default="USD"),
        sa.Column("base_nav", sa.Numeric(20, 8), default=100),
        sa.Column("total_units", sa.Numeric(28, 8), default=0),
        sa.Column("equity", sa.Numeric(20, 8), default=0),
        sa.Column("hwm", sa.Numeric(20, 8), default=0),
        sa.Column("performance_fee_rate", sa.Numeric(6, 4), default=0.2),
        sa.Column("management_fee_rate", sa.Numeric(6, 4), default=0),
        sa.Column("allocation_method", sa.String, default="euro_days"),
        sa.Column("nav_at_period_start", sa.Numeric(20, 8), default=100),
        sa.Column("manager_user_id", sa.String, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String, default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("broker_id", "login", name="uq_master_broker_login"),
    )
    op.create_table(
        "strategies",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("master_account_id", sa.String, sa.ForeignKey("master_accounts.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("kind", sa.String, default="pamm"),  # pamm|mam|copy
        sa.Column("status", sa.String, default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "investor_accounts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("broker_id", sa.String, sa.ForeignKey("brokers.id"), nullable=False),
        sa.Column("login", sa.String, nullable=False),
        sa.Column("currency", sa.String(3), default="USD"),
        sa.Column("owner_user_id", sa.String, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String, default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("broker_id", "login", name="uq_investor_broker_login"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("strategy_id", sa.String, sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("master_account_id", sa.String, sa.ForeignKey("master_accounts.id"), nullable=False),
        sa.Column("investor_account_id", sa.String, sa.ForeignKey("investor_accounts.id"), nullable=False),
        sa.Column("investor_user_id", sa.String, sa.ForeignKey("users.id")),
        sa.Column("units", sa.Numeric(28, 8), default=0),
        sa.Column("contributed_capital", sa.Numeric(20, 8), default=0),
        sa.Column("start_capital", sa.Numeric(20, 8), default=0),
        sa.Column("end_capital", sa.Numeric(20, 8), default=0),
        sa.Column("euro_days", sa.Numeric(28, 8), default=0),
        sa.Column("hwm", sa.Numeric(20, 8), default=0),
        sa.Column("status", sa.String, default="active"),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("detached_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "rollovers",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("master_account_id", sa.String, sa.ForeignKey("master_accounts.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String, nullable=False),
        sa.Column("master_equity_before", sa.Numeric(20, 8)),
        sa.Column("master_equity_after", sa.Numeric(20, 8)),
        sa.Column("master_pnl", sa.Numeric(20, 8)),
        sa.Column("total_units", sa.Numeric(28, 8)),
        sa.Column("nav_before", sa.Numeric(20, 8)),
        sa.Column("nav_after", sa.Numeric(20, 8)),
        sa.Column("total_performance_fee", sa.Numeric(20, 8), default=0),
        sa.Column("status", sa.String, default="completed"),
        sa.Column("idempotency_key", sa.String, unique=True),
        sa.Column("created_by", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "rollover_entries",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("rollover_id", sa.String, sa.ForeignKey("rollovers.id"), nullable=False),
        sa.Column("subscription_id", sa.String, sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("units", sa.Numeric(28, 8)),
        sa.Column("start_capital", sa.Numeric(20, 8)),
        sa.Column("end_capital", sa.Numeric(20, 8)),
        sa.Column("euro_days", sa.Numeric(28, 8)),
        sa.Column("pnl_share", sa.Numeric(20, 8)),
        sa.Column("performance_fee", sa.Numeric(20, 8)),
        sa.Column("nav_before", sa.Numeric(20, 8)),
        sa.Column("nav_after", sa.Numeric(20, 8)),
        sa.Column("units_after", sa.Numeric(28, 8)),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("event_id", sa.String, unique=True, nullable=False),
        sa.Column("type", sa.String, nullable=False),
        sa.Column("subject_type", sa.String),
        sa.Column("subject_id", sa.String),
        sa.Column("payload", sa.JSON, default={}),
        sa.Column("schema_version", sa.Integer, default=1),
        sa.Column("causation_id", sa.String),
        sa.Column("correlation_id", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_events_tenant_type", "events", ["tenant_id", "type"])
    op.create_index("ix_events_subject", "events", ["subject_type", "subject_id"])
    op.create_table(
        "outbox",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("event_id", sa.String, sa.ForeignKey("events.event_id"), nullable=False),
        sa.Column("status", sa.String, default="pending"),
        sa.Column("attempts", sa.Integer, default=0),
        sa.Column("last_error", sa.Text),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("actor_id", sa.String),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("resource_type", sa.String),
        sa.Column("resource_id", sa.String),
        sa.Column("before", sa.JSON),
        sa.Column("after", sa.JSON),
        sa.Column("reason", sa.Text),
        sa.Column("prev_hash", sa.String),
        sa.Column("hash", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_tenant", "audit_log", ["tenant_id"])
    op.create_table(
        "risk_rules",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("master_account_id", sa.String, sa.ForeignKey("master_accounts.id")),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("params", sa.JSON, default={}),
        sa.Column("version", sa.Integer, default=1),
        sa.Column("active", sa.Boolean, default=True),
        sa.Column("created_by", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "risk_rejections",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("master_account_id", sa.String),
        sa.Column("reason_code", sa.String, nullable=False),
        sa.Column("reason_details", sa.JSON),
        sa.Column("payload", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "settlement_leaves",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("rollover_id", sa.String, sa.ForeignKey("rollovers.id"), nullable=False),
        sa.Column("subscription_id", sa.String, nullable=False),
        sa.Column("canonical_blob", sa.Text, nullable=False),
        sa.Column("hash", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("rollover_id", "subscription_id", name="uq_leaf_rollover_sub"),
    )
    op.create_table(
        "settlement_roots",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("rollover_id", sa.String, sa.ForeignKey("rollovers.id"), unique=True, nullable=False),
        sa.Column("root_hash", sa.String, nullable=False),
        sa.Column("leaf_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---------- M2: MAM engine ----------
    op.create_table(
        "mam_child_orders",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("master_order_id", sa.String, nullable=False, index=True),
        sa.Column("master_account_id", sa.String, sa.ForeignKey("master_accounts.id"), nullable=False),
        sa.Column("subscription_id", sa.String, sa.ForeignKey("subscriptions.id"), nullable=False),
        sa.Column("investor_account_id", sa.String, nullable=False),
        sa.Column("symbol", sa.String, nullable=False),
        sa.Column("side", sa.String, nullable=False),  # buy|sell
        sa.Column("requested_lots", sa.Numeric(20, 8), nullable=False),
        sa.Column("allocated_lots", sa.Numeric(20, 8), nullable=False),
        sa.Column("residual_lots", sa.Numeric(20, 8), default=0),
        sa.Column("price", sa.Numeric(20, 8)),
        sa.Column("status", sa.String, default="pending"),  # pending|filled|rejected|partial
        sa.Column("filled_lots", sa.Numeric(20, 8), default=0),
        sa.Column("fill_price", sa.Numeric(20, 8)),
        sa.Column("reject_reason", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mam_child_master", "mam_child_orders", ["master_account_id"])

    # ---------- M2: Copy trading engine ----------
    op.create_table(
        "copy_subscriptions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("strategy_id", sa.String, sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("master_account_id", sa.String, sa.ForeignKey("master_accounts.id"), nullable=False),
        sa.Column("follower_account_id", sa.String, sa.ForeignKey("investor_accounts.id"), nullable=False),
        sa.Column("follower_user_id", sa.String, sa.ForeignKey("users.id")),
        sa.Column("status", sa.String, default="active"),  # active|paused|detached
        sa.Column("max_lots_per_trade", sa.Numeric(20, 8)),
        sa.Column("max_drawdown_pct", sa.Numeric(6, 4)),
        sa.Column("excluded_symbols", sa.JSON, default=[]),
        sa.Column("lot_multiplier", sa.Numeric(20, 8), default=1),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("detached_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "copy_trades",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("strategy_id", sa.String, nullable=False),
        sa.Column("master_account_id", sa.String, nullable=False),
        sa.Column("symbol", sa.String, nullable=False),
        sa.Column("side", sa.String, nullable=False),  # buy|sell|close
        sa.Column("master_lots", sa.Numeric(20, 8), nullable=False),
        sa.Column("master_price", sa.Numeric(20, 8)),
        sa.Column("status", sa.String, default="open"),  # open|filled|rejected|cancelled
        sa.Column("causation_id", sa.String, index=True),  # for causal ordering
        sa.Column("idempotency_key", sa.String, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "copy_follower_trades",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("copy_trade_id", sa.String, sa.ForeignKey("copy_trades.id"), nullable=False, index=True),
        sa.Column("copy_subscription_id", sa.String, sa.ForeignKey("copy_subscriptions.id"), nullable=False),
        sa.Column("follower_account_id", sa.String, nullable=False),
        sa.Column("requested_lots", sa.Numeric(20, 8), nullable=False),
        sa.Column("allocated_lots", sa.Numeric(20, 8), default=0),
        sa.Column("fill_price", sa.Numeric(20, 8)),
        sa.Column("status", sa.String, default="pending"),  # pending|filled|rejected|skipped
        sa.Column("reject_reason", sa.String),
        sa.Column("server_side_latency_ms", sa.Integer),  # server processing latency only
        sa.Column("broker_latency_ms", sa.Integer),  # broker/network/exchange latency
        sa.Column("slippage_bps", sa.Numeric(10, 4)),  # measured slippage in basis points
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---------- M2: Settlement saga (P-3) ----------
    op.create_table(
        "settlement_sagas",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("saga_id", sa.String, unique=True, nullable=False),
        sa.Column("kind", sa.String, nullable=False),  # rollover|mam_batch|copy_close_batch
        sa.Column("status", sa.String, default="pending"),  # pending|running|completed|compensating|failed|abandoned
        sa.Column("payload", sa.JSON, default={}),
        sa.Column("steps", sa.JSON, default=[]),  # ordered list of step descriptors
        sa.Column("completed_steps", sa.JSON, default=[]),
        sa.Column("failed_step", sa.String),
        sa.Column("failure_reason", sa.Text),
        sa.Column("compensation_log", sa.JSON, default=[]),
        sa.Column("idempotency_key", sa.String, index=True),
        sa.Column("created_by", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "saga_steps",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("saga_id", sa.String, sa.ForeignKey("settlement_sagas.saga_id"), nullable=False, index=True),
        sa.Column("step_name", sa.String, nullable=False),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("status", sa.String, default="pending"),  # pending|running|completed|failed|compensated|skipped
        sa.Column("request", sa.JSON),
        sa.Column("response", sa.JSON),
        sa.Column("error", sa.Text),
        sa.Column("attempts", sa.Integer, default=0),
        sa.Column("is_reversible", sa.Boolean, default=True),
        sa.Column("compensation_action", sa.String),  # reverse|remediate|manual
        sa.Column("compensation_payload", sa.JSON),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

def downgrade():
    for t in [
        "saga_steps","settlement_sagas","copy_follower_trades","copy_trades","copy_subscriptions",
        "mam_child_orders","settlement_roots","settlement_leaves","risk_rejections","risk_rules",
        "audit_log","outbox","events","rollover_entries","rollovers","subscriptions",
        "investor_accounts","strategies","master_accounts","trading_servers","brokers","users","tenants",
    ]:
        op.drop_table(t)
