"""SQL schema for Aria — multi-tenant salon bot platform."""

SCHEMA = """
-- ── Tenants ───────────────────────────────────────────────────────────────────
-- One row per salon / bot. Bot token + config stored here.
CREATE TABLE IF NOT EXISTS aria_tenants (
    id                      SERIAL PRIMARY KEY,
    bot_token               TEXT UNIQUE NOT NULL,
    owner_tg_id             BIGINT,
    salon_name              TEXT NOT NULL DEFAULT 'My Salon',
    owner_name              TEXT NOT NULL DEFAULT 'Owner',
    services                TEXT NOT NULL DEFAULT 'haircut, manicure',
    hours                   TEXT NOT NULL DEFAULT 'Mon-Sat 10:00-20:00',
    open_hour               INT  NOT NULL DEFAULT 10,
    close_hour              INT  NOT NULL DEFAULT 20,
    slot_minutes            INT  NOT NULL DEFAULT 60,
    working_days            TEXT NOT NULL DEFAULT '1,2,3,4,5,6',
    google_cal_credentials  TEXT,
    google_cal_id           TEXT,
    anthropic_api_key       TEXT,
    setup_complete          BOOLEAN NOT NULL DEFAULT FALSE,
    active                  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Per-tenant tables (new deployments get these directly) ────────────────────
CREATE TABLE IF NOT EXISTS aria_clients (
    tenant_id   INT     NOT NULL DEFAULT 1,
    user_id     BIGINT  NOT NULL,
    lang        TEXT    NOT NULL DEFAULT 'en',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS aria_bookings (
    id                  BIGSERIAL PRIMARY KEY,
    tenant_id           INT     NOT NULL DEFAULT 1,
    user_id             BIGINT  NOT NULL,
    client_name         TEXT    NOT NULL,
    service             TEXT    NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'confirmed',
    reminder_sent       BOOLEAN NOT NULL DEFAULT FALSE,
    noshow_check_sent   BOOLEAN NOT NULL DEFAULT FALSE,
    upsell_offered      BOOLEAN NOT NULL DEFAULT FALSE,
    calendar_event_id   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS aria_bookings_tenant_idx
    ON aria_bookings (tenant_id, scheduled_at)
    WHERE status = 'confirmed';

CREATE TABLE IF NOT EXISTS aria_waitlist (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   INT     NOT NULL DEFAULT 1,
    user_id     BIGINT  NOT NULL,
    client_name TEXT    NOT NULL,
    service     TEXT    NOT NULL,
    notified    BOOLEAN NOT NULL DEFAULT FALSE,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aria_conversations (
    tenant_id   INT     NOT NULL DEFAULT 1,
    user_id     BIGINT  NOT NULL,
    history     JSONB   NOT NULL DEFAULT '[]',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

-- ── Safe migration for databases created before multi-tenant ──────────────────
ALTER TABLE aria_clients     ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;
ALTER TABLE aria_bookings    ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;
ALTER TABLE aria_waitlist    ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;
ALTER TABLE aria_conversations ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;

-- Re-key aria_clients: drop old PK(user_id), add PK(tenant_id, user_id)
DO $$
DECLARE r TEXT;
BEGIN
    SELECT constraint_name INTO r FROM information_schema.table_constraints
    WHERE table_name='aria_clients' AND constraint_type='PRIMARY KEY';
    IF r IS NOT NULL AND r != 'aria_clients_pkey_new' THEN
        EXECUTE 'ALTER TABLE aria_clients DROP CONSTRAINT ' || r;
        ALTER TABLE aria_clients ADD PRIMARY KEY (tenant_id, user_id);
    END IF;
EXCEPTION WHEN others THEN NULL; END $$;

-- Re-key aria_conversations: drop old PK(user_id), add PK(tenant_id, user_id)
DO $$
DECLARE r TEXT;
BEGIN
    SELECT constraint_name INTO r FROM information_schema.table_constraints
    WHERE table_name='aria_conversations' AND constraint_type='PRIMARY KEY';
    IF r IS NOT NULL AND r != 'aria_conversations_pkey_new' THEN
        EXECUTE 'ALTER TABLE aria_conversations DROP CONSTRAINT ' || r;
        ALTER TABLE aria_conversations ADD PRIMARY KEY (tenant_id, user_id);
    END IF;
EXCEPTION WHEN others THEN NULL; END $$;
"""
