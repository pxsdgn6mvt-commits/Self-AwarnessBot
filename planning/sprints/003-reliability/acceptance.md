# Sprint 003 — Acceptance Criteria

## Must Pass

- [ ] В `_watch_tenants` есть проверка `scheduler.get_job(job_id)` перед
      регистрацией email-джоба
- [ ] Email-джоб не регистрируется дважды для одного тенанта
- [ ] Функция `_notify_admin` (или inline-эквивалент) существует в файле
      с `_run_reminder_scan`
- [ ] `_notify_admin` вызывается в except-блоке `_run_reminder_scan`
- [ ] `ARIA_BOT_TOKEN` / `ARIA_OWNER_TELEGRAM_ID` читаются из `os.getenv()`,
      не захардкожены
- [ ] В `menu.py` schedule callbacks: `except Exception: pass` заменён на
      `log.error` с `exc_info=True` (только для non-delete блоков)

## Should Pass

- [ ] `_notify_admin` не падает если `ARIA_OWNER_TELEGRAM_ID` не задан
      (graceful skip)
- [ ] `_notify_admin` не падает если Telegram недоступен
      (внутренний try/except)
- [ ] `api_create_booking` в `server.py` также уведомляет админа при падении

## NOT Checked

- Реальная доставка уведомлений (требует prod окружения)
- `miniapp/` файлы не проверять
