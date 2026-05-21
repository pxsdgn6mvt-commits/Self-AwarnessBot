# STATE.md — Aria Bot Platform
Последнее обновление: 2026-05-21

## Текущее состояние

| Компонент | Статус |
|---|---|
| Multi-tenant polling loop | ✅ работает |
| Owner FSM (quick.py) | ✅ работает |
| Client booking FSM (bot) | ✅ Sprint 002 done |
| client_phone в aria_bookings | ✅ промигрировано |
| Mini App | ❌ не существует |
| Client booking (Mini App) | ❌ не существует |
| GCal sync для клиентских броней | ❌ не реализовано |
| is_active фильтрация услуг | ❌ колонки нет в схеме |

## Последний завершённый спринт
Sprint 002 — Client Booking FSM in Bot
Ветка: claude/client-booking-fsm-sprint-05t0R
Коммит: a052aaf

## Активный спринт
Sprint 003 — Mini App Skeleton + API

## Зафиксированные паттерны
- callback_data с именами сущностей → хранить в FSM state (items_info dict),
  в callback передавать только ID (обход 64-байтного лимита Telegram)
- ALTER TABLE миграции — только IF NOT EXISTS, в блоке models.py
- server.py — не трогать никогда (соглашение проекта)

## Открытые технические долги
- TD-001: is_active отсутствует в aria_service_categories и aria_service_items.
  Клиент видит все услуги, включая те, что владелец хотел бы скрыть.
  → Закрыть в Sprint 004 (после Mini App)
- TD-002: Конфликты слотов не проверяются — клиент может записаться
  на уже занятое время. → Sprint 005
