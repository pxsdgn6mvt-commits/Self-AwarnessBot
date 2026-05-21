-- ============================================================
-- Sprint 007: Masters Schema
-- Applied automatically via aria/db/models.py SCHEMA on startup.
-- This file is kept as a reference / for manual psql application.
-- ============================================================

-- 1. Мастера тенанта
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

-- 2. Услуги мастера (many-to-many)
CREATE TABLE IF NOT EXISTS aria_master_services (
    master_id   INTEGER NOT NULL REFERENCES aria_masters(id) ON DELETE CASCADE,
    service_id  INTEGER NOT NULL REFERENCES aria_service_items(id) ON DELETE CASCADE,
    PRIMARY KEY (master_id, service_id)
);

-- 3. Переопределения доступности (поверх aria_tenants расписания)
--    date IS NOT NULL  → правило на конкретную дату (weekday = NULL)
--    weekday IS NOT NULL → еженедельное правило (date = NULL)
--    is_open = FALSE   → блок на весь день или слот
--    time_from/time_to = NULL + is_open = FALSE → весь день закрыт
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

-- 4. master_id в бронированиях (NULL = запись без привязки к мастеру)
ALTER TABLE aria_bookings
    ADD COLUMN IF NOT EXISTS master_id INTEGER REFERENCES aria_masters(id) ON DELETE SET NULL;
