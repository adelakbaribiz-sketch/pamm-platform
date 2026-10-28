"""m3: P-1 constrained allocation, P-2 latency prediction, outbox stats"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    # ---------- P-1: Risk-Constrained Adaptive Allocation ----------
    op.create_table(
        "allocation_problems",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("master_account_id", sa.String, nullable=False),
        sa.Column("session_id", sa.String, nullable=False, index=True),
        sa.Column("objective", sa.String, nullable=False),  # maximize_return|minimize_risk|balanced
        sa.Column("investor_ids", sa.JSON, nullable=False),  # ordered list
        sa.Column("constraints", sa.JSON, nullable=False),
        sa.Column("solver_status", sa.String, default="pending"),  # pending|optimal|infeasible|frozen|suboptimal
        sa.Column("solution", sa.JSON),  # dict[investor_id -> allocation]
        sa.Column("objective_value", sa.Numeric(20, 8)),
        sa.Column("infeasibility_reason", sa.Text),
        sa.Column("frozen", sa.Boolean, default=False),
        sa.Column("alert_emitted", sa.Boolean, default=False),
        sa.Column("created_by", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alloc_problems_master", "allocation_problems", ["master_account_id"])

    op.create_table(
        "allocation_alerts",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("allocation_problem_id", sa.String, sa.ForeignKey("allocation_problems.id"), nullable=False),
        sa.Column("master_account_id", sa.String, nullable=False),
        sa.Column("kind", sa.String, nullable=False),  # infeasible|constraint_violation|frozen
        sa.Column("details", sa.JSON),
        sa.Column("acknowledged", sa.Boolean, default=False),
        sa.Column("acknowledged_by", sa.String),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ---------- P-2: Shadow Latency & Slippage Prediction ----------
    op.create_table(
        "execution_profiles",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("destination", sa.String, nullable=False),  # broker|adapter|symbol:broker
        sa.Column("symbol", sa.String),  # NULL = profile applies to all symbols
        sa.Column("total_observations", sa.Integer, default=0),
        sa.Column("latency_mean_ms", sa.Numeric(12, 4)),
        sa.Column("latency_std_ms", sa.Numeric(12, 4)),
        sa.Column("latency_p50_ms", sa.Numeric(12, 4)),
        sa.Column("latency_p95_ms", sa.Numeric(12, 4)),
        sa.Column("latency_p99_ms", sa.Numeric(12, 4)),
        sa.Column("slippage_mean_bps", sa.Numeric(12, 4)),
        sa.Column("slippage_std_bps", sa.Numeric(12, 4)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "destination", "symbol", name="uq_profile_dest_symbol"),
    )

    op.create_table(
        "latency_predictions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("destination", sa.String, nullable=False),
        sa.Column("symbol", sa.String),
        sa.Column("order_size", sa.Numeric(20, 8)),
        sa.Column("features", sa.JSON),  # historical features at prediction time
        sa.Column("predicted_latency_ms", sa.Numeric(12, 4), nullable=False),
        sa.Column("predicted_lower_ms", sa.Numeric(12, 4)),  # 95% interval
        sa.Column("predicted_upper_ms", sa.Numeric(12, 4)),
        sa.Column("predicted_slippage_bps", sa.Numeric(12, 4)),
        sa.Column("actual_latency_ms", sa.Integer),
        sa.Column("actual_slippage_bps", sa.Numeric(12, 4)),
        sa.Column("residual_latency", sa.Numeric(12, 4)),
        sa.Column("residual_slippage", sa.Numeric(12, 4)),
        sa.Column("model_version", sa.String, default="v1-linear"),
        sa.Column("throttle_applied", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_latency_pred_dest", "latency_predictions", ["tenant_id", "destination"])

    op.create_table(
        "latency_observations",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False),
        sa.Column("destination", sa.String, nullable=False),
        sa.Column("symbol", sa.String),
        sa.Column("order_size", sa.Numeric(20, 8)),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("slippage_bps", sa.Numeric(12, 4)),
        sa.Column("prediction_id", sa.String, sa.ForeignKey("latency_predictions.id")),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_lat_obs_dest", "latency_observations", ["tenant_id", "destination"])

def downgrade():
    for t in ["latency_observations", "latency_predictions", "execution_profiles",
              "allocation_alerts", "allocation_problems"]:
        op.drop_table(t)
