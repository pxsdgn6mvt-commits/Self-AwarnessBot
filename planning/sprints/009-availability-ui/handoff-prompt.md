# Sprint 009 Handoff — Builder Instructions

## Read First (обязательно, в этом порядке)
1. docs/STATE.md
2. docs/DOMAIN.md — aria_availability (все поля и constraint),
   aria_tenants (open_hour, close_hour, slot_minutes)
3. planning/sprints/009-availability-ui/requirements.md
4. planning/sprints/009-availability-ui/blueprint.md
5. planning/sprints/009-availability-ui/acceptance.md

## Then Read Source Files
6. aria/handlers/masters.py — паттерн FSM и callback flow
7. aria/handlers/menu.py — паттерн cfg: хендлеров
8. aria/db/repo.py — паттерн CRUD (async with _p().acquire())
9. aria/main.py — где регистрируются роутеры

## Execute

### Step 1 — masters.py
В `_masters_text_and_kb()` добавить для каждого мастера кнопку
`[📅 Расписание]` → `callback_data=f"cfg:avail:{master_id}"`.

### Step 2 — aria/handlers/availability.py (новый файл)
Прочитать masters.py перед написанием — использовать тот же паттерн.
Реализовать все 6 хендлеров из blueprint:
- cfg:avail:{id} — главный экран
- cfg:avail_close:{id} — FSM закрытия дня
- cfg:avail_hours:{id} — FSM изменения часов
- cfg:avail_slot:{id} — FSM блокировки слота
- cfg:avail_list:{id} — список блокировок
- cfg:avail_del:{avail_id} — удаление

Для FSM слота: получить slot_minutes через
`get_tenant_slot_minutes(tenant_id)` из repo.py.

### Step 3 — repo.py
Добавить 4 функции используя паттерн
`async with _p().acquire() as conn`:
- create_availability()
- get_availability()
- delete_availability()
- get_tenant_slot_minutes()

### Step 4 — Регистрация роутера
Добавить `availability_router` в `_build_dispatcher()` в main.py
рядом с `masters_router`.

## Constraints
- НЕ трогать server.py и /api/slots
- НЕ трогать miniapp/
- НЕ трогать client_bot.py
- Если карточка мастера в masters.py реализована иначе чем
  предполагает blueprint — адаптировать, объяснить в Assumptions
- Валидация дат и времени обязательна — FSM не должен падать
  на невалидном вводе пользователя

## Completion Summary Format
### Files Created
### Files Modified
### FSM Pattern Used
### Validation Approach
### Assumptions Made
### Acceptance Criteria Status [✅/❌]
### Ready for Sprint 010: YES/NO
