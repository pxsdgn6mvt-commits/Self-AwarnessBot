# Sprint 003 Handoff — Builder Instructions

## Read First (обязательно, в этом порядке)

1. `docs/STATE.md`
2. `docs/DOMAIN.md`
3. `docs/DECISIONS.md`
4. `planning/sprints/003-reliability/requirements.md`
5. `planning/sprints/003-reliability/blueprint.md`
6. `planning/sprints/003-reliability/acceptance.md`

## Then Read Source Files

7. `development.md` — секции про APScheduler и email-мониторинг
8. `aria/main.py` — найти `_watch_tenants` и `start_email_job`
9. `aria/services/scheduler.py` — найти `_run_reminder_scan` и try/except блоки
10. `aria/handlers/menu.py` — найти schedule callback блоки
11. `server.py` — найти `api_create_booking`
12. `.env.example` — проверить `ARIA_OWNER_TELEGRAM_ID`

---

## Execute (строго по blueprint.md)

### Change 1 — Email Job Resurrection

В `aria/main.py` найти `_watch_tenants`.
Добавить проверку: если email-джоб для тенанта не зарегистрирован
в scheduler — вызвать `start_email_job`.
Использовать `get_scheduler().get_job(f"email_monitor_{tenant_id}")`.
Не менять сигнатуру `start_email_job`.

### Change 2 — Admin Notification

Найти `_run_reminder_scan` в `aria/services/scheduler.py`.
Добавить функцию `_notify_admin` локально в этот файл
(шаблон в `blueprint.md`).
Вызвать её в except-блоке `_run_reminder_scan`.
Повторить для `api_create_booking` в `server.py`.

### Change 3 — Logging в menu.py

Найти `except: pass` блоки в schedule callbacks (не в `message.delete`).
Заменить `pass` на `log.error` с `exc_info=True`.

---

## Constraints

- НЕ создавать новый модуль `notify_admin.py`
- НЕ трогать `miniapp/`
- НЕ трогать WebApp-кнопку в `start.py`
- НЕ менять схему БД
- Если `_run_reminder_scan` живёт в нескольких файлах — уведомить в summary
- Если `ARIA_OWNER_TELEGRAM_ID` уже есть в `.env.example` — отметить в summary
- Если его нет — добавить строку в `.env.example` с комментарием

---

## Completion Summary Format

```
Files Modified
[список с кратким описанием каждого изменения]

Files NOT Touched
Confirmed: miniapp/, start.py, схема БД не изменялись

Where _run_reminder_scan Lives
[точный файл и строка]

ADMIN_TELEGRAM_ID Status
[был в .env.example / добавлен / отсутствует и почему]

Assumptions Made
[неоднозначности и решения]

Acceptance Criteria Status
[чеклист с ✅ или ❌]

Ready for Sprint 004
YES / NO
```
