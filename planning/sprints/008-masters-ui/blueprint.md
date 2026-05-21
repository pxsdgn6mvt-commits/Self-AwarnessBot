# Sprint 008 — Blueprint

## Reading Order for Builder
1. docs/STATE.md
2. docs/DOMAIN.md — aria_masters структура (Sprint 007)
3. planning/sprints/008-masters-ui/requirements.md
4. aria/handlers/menu.py — полностью: паттерн cfg:, FSM, tenant_id
5. aria/db/repo.py — секция Masters (Sprint 007 CRUD)
6. aria/main.py — где регистрируются роутеры

## Change 1 — menu.py: кнопка в _owner_settings_kb()
Добавить [👥 Мастера] callback_data="cfg:masters" в сетку кнопок.

## Change 2 — aria/handlers/masters.py (новый файл)
Все хендлеры masters flow. Использовать реальный паттерн из menu.py.

- cb_masters_list: cfg:masters → список + кнопки
- cb_master_deactivate: cfg:master_off:{id} → confirm → is_active=FALSE
- cb_master_activate: cfg:master_on:{id} → is_active=TRUE без confirm
- AddMasterFSM: имя → телефон (пропускаемый) → create_master

Мастера-владельца (is_owner=TRUE) пометить 👑.
Деактивацию is_owner=TRUE — заблокировать с сообщением.

## Change 3 — repo.py: доп. функции
- set_master_active(master_id, is_active) — UPDATE is_active
- get_master_by_id(master_id) — для confirm диалога

## Change 4 — Регистрация masters_router в main.py

## Files NOT to Touch
miniapp/, server.py, client_bot.py, start.py, scheduler.py
