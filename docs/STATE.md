# STATE.md — Aria Bot Platform
Последнее обновление: 2026-05-21

## Статус компонентов

Multi-tenant polling loop        ✅
Owner FSM (quick.py)             ✅
Client booking FSM (bot)         ✅ Sprint 002
client_phone в aria_bookings     ✅ Sprint 002
notify_owner (notifications.py)  ✅ Sprint 003
aiohttp API в aria/main.py       ✅ Sprint 003
Mini App (miniapp/)              ✅ Sprint 003
is_active фильтрация услуг       ❌ TD-001 → Sprint 004
Конфликты слотов                 ❌ TD-002 → Sprint 005
GCal sync клиентских броней      ❌ → Sprint 006

## Последние спринты

Sprint 002 — Client Booking FSM
  ветка: claude/client-booking-fsm-sprint-05t0R
  коммит: a052aaf

Sprint 003 — Mini App + API
  ветка: claude/api-layer-aiohttp-main-qRfj3
  коммит: 60bada9

## Активный спринт

Sprint 004 — is_active filtering (TD-001)

## Критические факты для Builder

_bots: ключ int(tenant_id), не строка bot_token
repo.create_booking(): перед использованием читать реальную сигнатуру в repo.py
aria_service_items: колонка duration_minutes, не duration_min
initData: user_id парсится из initData.user.id
server.py: не трогать (Flask, маркетинг)
aiohttp API: живёт в aria/main.py, порт PORT_API (default 8081)

## Railway Variables

ARIA_BOT_TOKEN    required   —      Main bot token
DATABASE_URL      required   —      asyncpg DSN
ANTHROPIC_API_KEY required   —      AI responses
PORT_API          optional   8081   aiohttp Mini App API port
