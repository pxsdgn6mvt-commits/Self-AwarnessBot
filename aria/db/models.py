"""
SQL schema for the Aria salon bot.
All tables are prefixed with aria_ to avoid collisions with other bots
that might share the same Postgres instance.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS aria_clients (
    user_id     BIGINT PRIMARY KEY,
    name        TEXT,
    lang        TEXT    NOT NULL DEFAULT 'en',
    phone       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aria_bookings (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             BIGINT  NOT NULL,
    client_name         TEXT    NOT NULL,
    service             TEXT    NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'confirmed',
    -- confirmed | cancelled | completed | no_show
    reminder_sent       BOOLEAN NOT NULL DEFAULT FALSE,
    noshow_check_sent   BOOLEAN NOT NULL DEFAULT FALSE,
    calendar_event_id   TEXT,
    upsell_offered      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS aria_bookings_user_idx
    ON aria_bookings (user_id);
CREATE INDEX IF NOT EXISTS aria_bookings_scheduled_idx
    ON aria_bookings (scheduled_at)
    WHERE status = 'confirmed';

CREATE TABLE IF NOT EXISTS aria_waitlist (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT  NOT NULL,
    client_name TEXT    NOT NULL,
    service     TEXT    NOT NULL,
    notified    BOOLEAN NOT NULL DEFAULT FALSE,
    added_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS aria_waitlist_service_idx
    ON aria_waitlist (service)
    WHERE notified = FALSE;

-- Stores per-user conversation history for Claude (JSONB array of message objects)
CREATE TABLE IF NOT EXISTS aria_conversations (
    user_id     BIGINT PRIMARY KEY,
    history     JSONB   NOT NULL DEFAULT '[]',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Service catalogue managed by the salon owner via /admin
CREATE TABLE IF NOT EXISTS aria_service_categories (
    id       SERIAL PRIMARY KEY,
    name     TEXT    NOT NULL UNIQUE,
    position INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS aria_service_items (
    id          SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES aria_service_categories(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (category_id, name)
);
"""
