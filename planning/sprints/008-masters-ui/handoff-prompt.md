# Sprint 008 Handoff — Builder Instructions

## Read First
1. docs/STATE.md
2. docs/DOMAIN.md — aria_masters (поля, типы)
3. planning/sprints/008-masters-ui/requirements.md
4. planning/sprints/008-masters-ui/blueprint.md
5. planning/sprints/008-masters-ui/acceptance.md

## Then Read Source Files
6. aria/handlers/menu.py — полностью (паттерн cfg:, tenant_id, FSM)
7. aria/db/repo.py — секция Masters
8. aria/main.py — где регистрируются роутеры

## Execute

### Step 1 — menu.py
Добавить [👥 Мастера] callback_data="cfg:masters" в _owner_settings_kb().

### Step 2 — aria/handlers/masters.py
Все хендлеры по blueprint. Реальный паттерн из menu.py.
Владелец 👑, деактивация is_owner=TRUE — заблокировать.

### Step 3 — repo.py
set_master_active(master_id, is_active).
get_master_by_id(master_id) если нужен для confirm.

### Step 4 — Регистрация masters_router

## Constraints
- НЕ трогать miniapp/, server.py, client_bot.py, start.py
- НЕ добавлять привязку услуг
- НЕ создавать /masters команду

## Completion Summary Format
### Files Created/Modified
### Pattern Found in menu.py
### Owner Master Protection
### Assumptions Made
### Acceptance Criteria Status [✅/❌]
### Ready for Sprint 009: YES/NO
