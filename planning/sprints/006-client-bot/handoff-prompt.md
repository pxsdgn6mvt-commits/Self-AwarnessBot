# Sprint 006 Handoff — Builder Instructions

## Read First (обязательно, в этом порядке)
1. docs/STATE.md
2. docs/DOMAIN.md — структура aria_bookings, ищи client_tg_id
3. docs/DECISIONS.md
4. planning/sprints/006-client-bot/requirements.md
5. planning/sprints/006-client-bot/blueprint.md
6. planning/sprints/006-client-bot/acceptance.md

## Then Read Source Files
7. development.md — секции multi-tenant, main.py, polling
8. aria/main.py — полностью, понять как запускаются боты
9. aria/handlers/start.py — паттерн /start хендлера
10. server.py — найти POST /api/bookings и _tg_notify()
11. aria/config.py — паттерн env vars
12. .env.example — найти куда добавить CLIENT_BOT_TOKEN

## Execute

### Step 1 — aria/handlers/client_bot.py
Создать новый файл. Реализовать /start хендлер:
- Извлечь tenant_id из args (формат: /start tenant_123)
- Если нет tenant_id — ответить с инструкцией использовать ссылку мастера
- Если есть — отправить WebApp кнопку с URL: `f"{MINIAPP_URL}?tenant_id={tenant_id}"`
Адаптировать под реальный паттерн из aria/handlers/start.py.

### Step 2 — aria/main.py
Найти где инициализируется owner-бот. Добавить рядом инициализацию client_bot:
- Читать CLIENT_BOT_TOKEN из os.getenv()
- Если токен есть — создать Bot + включить client_router в отдельный Dispatcher
- Если нет — log.warning и продолжить без client_bot
Добавить client_bot polling в существующий asyncio.gather или аналог.

### Step 3 — server.py
Найти POST /api/bookings.

**3a. client_tg_id:**
- Проверить есть ли колонка в aria_bookings (читать DOMAIN.md)
- Принять client_tg_id из request body как опциональное поле
- Сохранить в БД если колонка есть
- Если колонки нет — написать нужный ALTER TABLE SQL в summary, НЕ выполнять

**3b. Уведомление мастеру:**
- Найти реальную сигнатуру _tg_notify()
- Получить owner_telegram_id и bot_token тенанта из БД
- Вызвать _tg_notify() с текстом уведомления после успешного INSERT
- Текст: имя клиента, услуга, дата, время, пометка "через Mini App"

### Step 4 — .env.example
Добавить CLIENT_BOT_TOKEN с комментарием.

## Constraints
- НЕ трогать miniapp/
- НЕ трогать aria/handlers/start.py
- НЕ выполнять ALTER TABLE автоматически — только SQL в summary
- НЕ ломать существующий owner-бот polling
- Если polling в main.py сложно расширить — описать в Assumptions

## Completion Summary Format

### Files Created
[список]

### Files Modified
[список с описанием изменений]

### client_tg_id Status
[есть в aria_bookings / нет — и SQL для миграции если нет]

### _tg_notify Signature Found
[реальная сигнатура из server.py]

### Assumptions Made
[неоднозначности и решения]

### Acceptance Criteria Status
[чеклист с ✅ или ❌]

### Manual Steps Required
1. BotFather → создать бота → CLIENT_BOT_TOKEN
2. Railway → добавить CLIENT_BOT_TOKEN
3. Cloudflare Pages → VITE_API_BASE (из Sprint 002)
4. [SQL миграция если нужна]

### Ready for Sprint 007
YES / NO
