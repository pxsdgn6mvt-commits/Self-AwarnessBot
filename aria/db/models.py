"""SQL schema for Aria — multi-tenant salon bot platform."""

SCHEMA = """
-- ── Tenants ───────────────────────────────────────────────────────────────────
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

-- ── Core tables (IF NOT EXISTS — safe for both fresh and existing DBs) ────────
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

-- ── Migrations ────────────────────────────────────────────────────────────────
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS timezone TEXT NOT NULL DEFAULT 'UTC';
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_host     TEXT;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_port     INT  NOT NULL DEFAULT 993;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_user     TEXT;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_password TEXT;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_folder       TEXT NOT NULL DEFAULT 'INBOX';
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_last_uid     TEXT;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_filter_type  TEXT NOT NULL DEFAULT 'all';
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS email_filter_value TEXT;

-- Must run BEFORE any CREATE INDEX that references tenant_id.
ALTER TABLE aria_clients      ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;
ALTER TABLE aria_bookings     ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;
ALTER TABLE aria_waitlist     ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;
ALTER TABLE aria_conversations ADD COLUMN IF NOT EXISTS tenant_id INT NOT NULL DEFAULT 1;

-- ── Indexes (after migration so tenant_id is guaranteed to exist) ─────────────
CREATE INDEX IF NOT EXISTS aria_bookings_tenant_idx
    ON aria_bookings (tenant_id, scheduled_at)
    WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS aria_waitlist_service_idx
    ON aria_waitlist (tenant_id, service)
    WHERE notified = FALSE;

-- ── Re-key aria_clients: old PK was user_id, new PK is (tenant_id, user_id) ──
DO $$
DECLARE r TEXT;
BEGIN
    SELECT constraint_name INTO r FROM information_schema.table_constraints
    WHERE table_name = 'aria_clients' AND constraint_type = 'PRIMARY KEY';
    -- Only migrate if the PK is the old single-column one
    IF r IS NOT NULL AND r != 'aria_clients_pkey' THEN
        NULL; -- already composite, nothing to do
    ELSIF r = 'aria_clients_pkey' THEN
        -- Check if it's actually on just user_id (old schema)
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.key_column_usage
            WHERE table_name = 'aria_clients'
              AND constraint_name = r
              AND column_name = 'tenant_id'
        ) THEN
            EXECUTE 'ALTER TABLE aria_clients DROP CONSTRAINT ' || r;
            ALTER TABLE aria_clients ADD PRIMARY KEY (tenant_id, user_id);
        END IF;
    END IF;
EXCEPTION WHEN others THEN NULL;
END $$;

-- ── Re-key aria_conversations: old PK was user_id ────────────────────────────
DO $$
DECLARE r TEXT;
BEGIN
    SELECT constraint_name INTO r FROM information_schema.table_constraints
    WHERE table_name = 'aria_conversations' AND constraint_type = 'PRIMARY KEY';
    IF r IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.key_column_usage
            WHERE table_name = 'aria_conversations'
              AND constraint_name = r
              AND column_name = 'tenant_id'
        ) THEN
            EXECUTE 'ALTER TABLE aria_conversations DROP CONSTRAINT ' || r;
            ALTER TABLE aria_conversations ADD PRIMARY KEY (tenant_id, user_id);
        END IF;
    END IF;
EXCEPTION WHEN others THEN NULL;
END $$;
"""
