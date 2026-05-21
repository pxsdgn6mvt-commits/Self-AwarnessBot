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
    paid                BOOLEAN NOT NULL DEFAULT FALSE,
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS paid  BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS notes TEXT;

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

-- ── Persistent FSM state (survives restarts) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_fsm_states (
    key   TEXT PRIMARY KEY,
    state TEXT,
    data  JSONB NOT NULL DEFAULT '{}'
);

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

-- ── CRM columns ───────────────────────────────────────────────────────────────
ALTER TABLE aria_clients ADD COLUMN IF NOT EXISTS communication_style TEXT NOT NULL DEFAULT 'casual';
ALTER TABLE aria_clients ADD COLUMN IF NOT EXISTS is_vip              BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE aria_clients ADD COLUMN IF NOT EXISTS vip_until           TIMESTAMPTZ;
ALTER TABLE aria_clients ADD COLUMN IF NOT EXISTS reactivation_sent   BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE aria_clients ADD COLUMN IF NOT EXISTS notes               TEXT;

-- ── Service catalogue (categories / subcategories) ────────────────────────────
CREATE TABLE IF NOT EXISTS aria_service_categories (
    id        SERIAL PRIMARY KEY,
    tenant_id INT  NOT NULL DEFAULT 1,
    name      TEXT NOT NULL,
    position  INT  NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS aria_service_items (
    id               SERIAL PRIMARY KEY,
    category_id      INT     NOT NULL REFERENCES aria_service_categories(id) ON DELETE CASCADE,
    name             TEXT    NOT NULL,
    position         INT     NOT NULL DEFAULT 0,
    price            NUMERIC(10,2),
    duration_minutes INT,
    UNIQUE (category_id, name)
);

ALTER TABLE aria_service_items ADD COLUMN IF NOT EXISTS price            NUMERIC(10,2);
ALTER TABLE aria_service_items ADD COLUMN IF NOT EXISTS duration_minutes INT;

ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS master_percent        NUMERIC(5,2);
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS tax_percent           NUMERIC(5,2);
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS reminder_hours_before INT NOT NULL DEFAULT 2;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS daily_summary_hour    INT NOT NULL DEFAULT 20;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS owner_lang            VARCHAR(2) NOT NULL DEFAULT 'ru';
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS is_vip                BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE aria_tenants ADD COLUMN IF NOT EXISTS vip_until             TIMESTAMPTZ;

-- ── S1-B: client reminders ────────────────────────────────────────────────────
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS client_tg_id         BIGINT;
ALTER TABLE aria_bookings ADD COLUMN IF NOT EXISTS client_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE;

-- ── S3-A: masters schema ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aria_masters (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES aria_tenants(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    phone       TEXT,
    telegram_id BIGINT,
    is_owner    BOOLEAN NOT NULL DEFAULT FALSE,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_masters_tenant
    ON aria_masters(tenant_id);

CREATE TABLE IF NOT EXISTS aria_master_services (
    master_id   INTEGER NOT NULL REFERENCES aria_masters(id) ON DELETE CASCADE,
    service_id  INTEGER NOT NULL REFERENCES aria_service_items(id) ON DELETE CASCADE,
    PRIMARY KEY (master_id, service_id)
);

-- Переопределения доступности поверх базового расписания в aria_tenants.
-- date IS NOT NULL + weekday IS NULL  → правило на конкретную дату
-- date IS NULL + weekday IS NOT NULL  → еженедельное правило (1=Пн..7=Вс)
-- time_from/time_to IS NULL           → правило на весь день
CREATE TABLE IF NOT EXISTS aria_availability (
    id          SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES aria_tenants(id) ON DELETE CASCADE,
    master_id   INTEGER REFERENCES aria_masters(id) ON DELETE CASCADE,
    date        DATE,
    weekday     SMALLINT,
    time_from   TIME,
    time_to     TIME,
    is_open     BOOLEAN NOT NULL DEFAULT FALSE,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_date_or_weekday CHECK (
        (date IS NOT NULL AND weekday IS NULL) OR
        (date IS NULL AND weekday IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_availability_tenant_date
    ON aria_availability(tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_availability_master_date
    ON aria_availability(master_id, date);

ALTER TABLE aria_bookings
    ADD COLUMN IF NOT EXISTS master_id INTEGER REFERENCES aria_masters(id) ON DELETE SET NULL;

-- ── S4: master bot tokens ──────────────────────────────────────────────────────
ALTER TABLE aria_masters ADD COLUMN IF NOT EXISTS bot_token  TEXT;
ALTER TABLE aria_masters ADD COLUMN IF NOT EXISTS bot_active BOOLEAN NOT NULL DEFAULT FALSE;
"""
