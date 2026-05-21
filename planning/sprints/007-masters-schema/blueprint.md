# Sprint 007 — Blueprint

## Reading Order for Builder
1. docs/STATE.md
2. docs/DOMAIN.md — полная схема aria_tenants, aria_bookings
3. docs/DECISIONS.md
4. planning/sprints/007-masters-schema/requirements.md
5. development.md — секция Database Schema
6. aria/db/repo.py — полностью, зафиксировать паттерн CRUD
7. aria/main.py — найти инициализацию тенантов при старте

## Change 1 — aria/db/migrations/007_masters_schema.sql

```sql
-- Sprint 007: Masters Schema

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
CREATE INDEX IF NOT EXISTS idx_masters_tenant ON aria_masters(tenant_id);

-- 2. Услуги мастера (many-to-many)
CREATE TABLE IF NOT EXISTS aria_master_services (
    master_id   INTEGER NOT NULL REFERENCES aria_masters(id) ON DELETE CASCADE,
    service_id  INTEGER NOT NULL REFERENCES aria_service_items(id) ON DELETE CASCADE,
    PRIMARY KEY (master_id, service_id)
);

-- 3. Переопределения доступности
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
CREATE INDEX IF NOT EXISTS idx_availability_tenant_date ON aria_availability(tenant_id, date);
CREATE INDEX IF NOT EXISTS idx_availability_master_date ON aria_availability(master_id, date);

-- 4. master_id в бронированиях
ALTER TABLE aria_bookings
    ADD COLUMN IF NOT EXISTS master_id INTEGER REFERENCES aria_masters(id) ON DELETE SET NULL;
```

## Change 2 — repo.py CRUD

Добавить 4 функции. Прочитать существующий паттерн перед написанием.

- create_master(pool, tenant_id, name, is_owner, phone, telegram_id) → int
- get_masters(pool, tenant_id, active_only=True) → list[dict]
- get_owner_master(pool, tenant_id) → dict | None
- ensure_owner_master(pool, tenant_id, owner_name) → int  # idempotent

## Change 3 — main.py

Найти где инициализируются тенанты при старте.
Добавить ensure_owner_master для каждого активного тенанта.

## Change 4 — docs/DOMAIN.md

Добавить aria_masters, aria_master_services, aria_availability.
Обновить aria_bookings — добавить master_id.

## Files NOT to Touch
- miniapp/, server.py (/api/slots), aria/handlers/, scheduler.py
