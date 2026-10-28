"""m3: drop outbox.event_id FK so orphaned outbox rows can persist (dead-letter support)"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    # Drop the FK constraint if present (allows outbox rows to outlive their events
    # when archived — important for dead-letter scenarios in production)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'outbox_event_id_fkey'
                  AND table_name = 'outbox'
            ) THEN
                ALTER TABLE outbox DROP CONSTRAINT outbox_event_id_fkey;
            END IF;
        END $$;
    """)

def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'outbox_event_id_fkey'
                  AND table_name = 'outbox'
            ) THEN
                ALTER TABLE outbox
                ADD CONSTRAINT outbox_event_id_fkey
                FOREIGN KEY (event_id) REFERENCES events(event_id);
            END IF;
        END $$;
    """)
