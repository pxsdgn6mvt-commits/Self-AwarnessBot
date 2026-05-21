# Sprint 007 Handoff — Builder Instructions

## Read First
1. docs/STATE.md
2. docs/DOMAIN.md — полная схема БД
3. docs/DECISIONS.md
4. planning/sprints/007-masters-schema/requirements.md
5. planning/sprints/007-masters-schema/blueprint.md
6. planning/sprints/007-masters-schema/acceptance.md

## Then Read Source Files
7. development.md — секция Database Schema
8. aria/db/repo.py — полностью, зафиксировать паттерн CRUD
9. aria/main.py — найти инициализацию тенантов при старте

## Execute

### Step 1 — SQL миграция
Создать aria/db/migrations/007_masters_schema.sql.
SQL из blueprint — использовать точно как написан.
IF NOT EXISTS везде.

### Step 2 — repo.py CRUD
Прочитать паттерн. Добавить 4 функции.
ensure_owner_master — idempotent (SELECT first, INSERT only if not exists).

### Step 3 — main.py
Найти инициализацию тенантов. Добавить ensure_owner_master вызов.

### Step 4 — docs/DOMAIN.md
Добавить 3 новые таблицы. Обновить aria_bookings.

## Constraints
- НЕ трогать miniapp/, server.py, aria/handlers/, scheduler.py
- НЕ применять миграцию автоматически
- НЕ ломать существующие CRUD функции

## Completion Summary Format

### Files Created / Modified
[список]

### CRUD Pattern Found
[как устроены существующие функции — async, pool vs conn]

### ensure_owner_master Logic
[как реализована idempotency]

### Manual Steps Required
Применить миграцию:
psql $DATABASE_URL -f aria/db/migrations/007_masters_schema.sql

### Acceptance Criteria Status
[чеклист ✅/❌]

### Ready for Sprint 008
YES / NO
