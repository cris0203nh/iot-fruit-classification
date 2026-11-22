"""Suscripciones comerciales DEMO; sin inserciones ni cambios operativos."""
from alembic import op

revision = 'c009commerce'
down_revision = 's007iot'
branch_labels = None
depends_on = None

# DDL congelado: no importa modelos futuros.
DDL = (
    """CREATE TABLE commercial_plans (
    id INTEGER NOT NULL,
    code VARCHAR(40) NOT NULL,
    version INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL,
    amount_cents INTEGER NOT NULL,
    currency VARCHAR(3) NOT NULL,
    period VARCHAR(10) NOT NULL,
    benefits_json TEXT NOT NULL,
    limits_json TEXT NOT NULL,
    is_active BOOLEAN NOT NULL,
    recommended BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_commercial_plan_version UNIQUE (code, version),
    CONSTRAINT ck_plan_price CHECK (amount_cents >= 0 AND amount_cents <= 100000000),
    CONSTRAINT ck_plan_period CHECK (period IN ('monthly','annual') AND currency = 'PEN')
)""",
    """CREATE TABLE commercial_subscriptions (
    id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    status VARCHAR(12) NOT NULL,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    organization_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_subscription_company UNIQUE (organization_id),
    CONSTRAINT ck_subscription_status CHECK (status IN ('active','cancelled')),
    CONSTRAINT ck_subscription_dates CHECK (ends_at > starts_at),
    FOREIGN KEY(plan_id) REFERENCES commercial_plans (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id),
    CONSTRAINT uq_commercial_subscriptions_org_pk UNIQUE (organization_id, id)
)""",
    """CREATE INDEX ix_commercial_subscriptions_ends_at ON commercial_subscriptions (ends_at)""",
    """CREATE TABLE commercial_orders (
    id VARCHAR(36) NOT NULL,
    idempotency_key VARCHAR(80) NOT NULL,
    plan_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    action VARCHAR(12) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at DATETIME NOT NULL,
    organization_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_order_idempotency UNIQUE (organization_id, idempotency_key),
    CONSTRAINT ck_order_status CHECK (status IN ('pending','demo_approved','demo_rejected','cancelled')),
    CONSTRAINT ck_order_action CHECK (action IN ('subscribe','change','renew')),
    CONSTRAINT ck_order_price CHECK (amount_cents >= 0),
    FOREIGN KEY(plan_id) REFERENCES commercial_plans (id),
    FOREIGN KEY(created_by) REFERENCES users (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id),
    CONSTRAINT uq_commercial_orders_org_pk UNIQUE (organization_id, id)
)""",
    """CREATE TABLE commercial_transactions (
    id INTEGER NOT NULL,
    order_id VARCHAR(36),
    actor_id INTEGER NOT NULL,
    outcome VARCHAR(24) NOT NULL,
    amount_cents INTEGER NOT NULL,
    created_at DATETIME NOT NULL,
    organization_id INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_demo_transaction_order UNIQUE (order_id),
    CONSTRAINT ck_demo_outcome CHECK (outcome IN ('demo_approved','demo_rejected','cancelled','subscription_cancelled')),
    FOREIGN KEY(actor_id) REFERENCES users (id),
    FOREIGN KEY(organization_id) REFERENCES organizations (id),
    CONSTRAINT uq_commercial_transactions_org_pk UNIQUE (organization_id, id),
    CONSTRAINT fk_commercial_transactions_org_order_id FOREIGN KEY(organization_id, order_id) REFERENCES commercial_orders (organization_id, id)
)""",
    """CREATE INDEX ix_commercial_transactions_org_order_id ON commercial_transactions (organization_id, order_id)""",
)

def upgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    for statement in DDL:
        op.execute(statement)

def downgrade():
    bind = op.get_bind()
    if not bind.connection.driver_connection.in_transaction:
        bind.exec_driver_sql('BEGIN IMMEDIATE')
    # Reversion explicita elimina solo datos DEMO comerciales. Exportar antes.
    for name in ('commercial_transactions','commercial_orders','commercial_subscriptions','commercial_plans'):
        op.drop_table(name)
