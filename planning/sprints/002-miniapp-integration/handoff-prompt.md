# Sprint 002 Handoff — Builder Instructions

## Read First (обязательно, в этом порядке)

1. `docs/STATE.md`
2. `docs/DOMAIN.md` — найти тип поля `working_days` у тенанта
3. `docs/DECISIONS.md`
4. `planning/sprints/002-miniapp-integration/requirements.md`
5. `planning/sprints/002-miniapp-integration/blueprint.md`
6. `planning/sprints/002-miniapp-integration/acceptance.md`

## Then Read Source Files

7. `aria/handlers/menu.py` — найти хендлер клиентского `/start` или меню
8. `server.py` — найти эндпоинт `/api/services`
9. `miniapp/src/screens/DateScreen.tsx` — найти логику генерации дат
10. `miniapp/src/api.ts` — подтвердить строку с `VITE_API_BASE`

---

## Execute (строго по blueprint.md)

### Change 1 — WebApp кнопка в боте

Найти в `aria/handlers/menu.py` (или смежном файле) хендлер,
который отвечает клиенту на `/start` или открытие меню.
Добавить `InlineKeyboardButton` с `WebAppInfo`.
URL формировать как: `f"{MINIAPP_URL}?tenant_id={tenant.id}"`
`MINIAPP_URL` брать из `os.getenv("MINIAPP_URL", "")`.
Не создавать новых хендлеров если подходящий уже есть.

### Change 2 — `working_days` в `/api/services`

В `server.py` найти маршрут `/api/services`.
Добавить поле `working_days` в возвращаемый JSON.
Тип поля взять из реальной модели тенанта (прочитать код, не угадывать).

### Change 3 — фильтр нерабочих дней в DateScreen

В `miniapp/src/screens/DateScreen.tsx` найти место где генерируются
доступные даты.
Добавить фильтрацию: показывать только дни, которые входят в `working_days`.
`working_days` получать из уже существующего вызова `/api/services`.
Не переписывать компонент — минимальное хирургическое изменение.

---

## Constraints

- НЕ трогать APScheduler, `_run_reminder_scan`, email-джобы
- НЕ создавать новые файлы
- НЕ менять схему БД
- НЕ менять `_tg_notify()`
- Если `working_days` имеет неожиданный тип — остановиться и описать
  проблему в summary, не угадывать

---

## Manual Step — напомнить в summary

После деплоя человек должен вручную:

1. Cloudflare Pages → Environment Variables
2. Добавить `VITE_API_BASE = https://<railway-web-url>`
3. Trigger redeploy

---

## Completion Summary Format

```
Files Modified
[список файлов с кратким описанием изменения]

Files NOT Touched
Confirmed: APScheduler-код, email-джобы, схема БД не изменялись

Type of working_days
[что реально нашёл в коде — тип, формат значений]

Assumptions Made
[любые неоднозначности и как разрешил]

Acceptance Criteria Status
[чеклист из acceptance.md с ✅ или ❌]

Manual Steps Required
[Cloudflare Pages инструкция]

Ready for Sprint 003
YES / NO
```
