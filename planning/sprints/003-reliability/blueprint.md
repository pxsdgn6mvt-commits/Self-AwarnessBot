# Sprint 003 — Blueprint

## Reading Order for Builder
1. `docs/STATE.md`
2. `docs/DOMAIN.md`
3. `docs/DECISIONS.md`
4. `planning/sprints/003-reliability/requirements.md`
5. `development.md` — секции про APScheduler, email-джобы, `_watch_tenants`
6. `aria/main.py` — найти `_watch_tenants` и `start_email_job`
7. `aria/handlers/menu.py` — найти `except: pass` блоки в schedule callbacks
8. `aria/services/scheduler.py` — найти `_run_reminder_scan` и try/except
9. `.env.example` — проверить наличие `ADMIN_TELEGRAM_ID`

---

## Change 1 — Email Job Resurrection

### Где смотреть
`aria/main.py` — функция `_watch_tenants` (периодически опрашивает тенантов).

### Что сделать
При каждой итерации `_watch_tenants` проверять: зарегистрирован ли
email-джоб для этого тенанта в scheduler. Если нет — регистрировать заново.

Псевдокод:
```python
for tenant in active_tenants:
    job_id = f"email_monitor_{tenant.id}"
    if not scheduler.get_job(job_id):
        start_email_job(tenant)  # существующая функция
```

Если `scheduler.get_job()` недоступен в текущем контексте — прочитать
как APScheduler используется в проекте и адаптировать.
Не менять сигнатуру `start_email_job`.

---

## Change 2 — Admin Notification при критических падениях

### Где смотреть
- Файл где живёт `_run_reminder_scan`
- `server.py` — функция `api_create_booking`

### Что сделать
В except-блоках критических джобов добавить отправку сообщения админу.
Использовать прямой вызов Telegram Bot API (как уже делает `_tg_notify()`
в `server.py`) — не импортировать aiogram bot объект если это сложно.

Шаблон (добавить локально в нужный файл, не выносить в модуль):
```python
import os, urllib.request, json as _json

def _notify_admin(context: str, error: Exception) -> None:
    token    = os.getenv("ARIA_BOT_TOKEN", "") or os.getenv("BOT_TOKEN", "")
    admin_id = os.getenv("ARIA_OWNER_TELEGRAM_ID", "") or os.getenv("OWNER_ID", "")
    if not token or not admin_id:
        return
    text = f"🚨 Aria error in {context}:\n{type(error).__name__}: {error}"
    data = _json.dumps({"chat_id": admin_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # не падать если уведомление не доставлено
```

Вызывать в except-блоках `_run_reminder_scan` и `api_create_booking`.

---

## Change 3 — Логирование в menu.py schedule callbacks

### Где смотреть
`aria/handlers/menu.py` — callbacks типа `cb_sched_today` и аналогичные.

### Что сделать
Найти `except Exception: pass` блоки которые оборачивают
импорт/вызов хендлеров (не блоки `message.delete()`).
Заменить `pass` на `log.error(f"...: {e}", exc_info=True)`.

Блоки `try: await message.delete() except: pass` — **НЕ трогать**, они нормальные.

---

## Files to Modify

| Файл | Изменение |
|---|---|
| `aria/main.py` | Email job resurrection в `_watch_tenants` |
| `aria/services/scheduler.py` | `_notify_admin` + вызов в except |
| `server.py` | `_notify_admin` + вызов в except `api_create_booking` |
| `aria/handlers/menu.py` | `log.error` вместо `pass` в schedule callbacks |

## Files NOT to Touch
- `miniapp/` — любые файлы
- `aria/handlers/start.py` — WebApp-кнопка уже работает
- Схема БД
- APScheduler конфигурация (только добавляем `get_job` проверку)
