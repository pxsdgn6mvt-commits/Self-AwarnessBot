# Sprint 003 — Mini App Skeleton + Booking API
## Статус: ACTIVE
## Дата: 2026-05-21

## Бизнес-цель
Создать работающий Telegram Mini App, через который клиент салона
может записаться на услугу. Это второй канал записи (первый — бот FSM,
Sprint 002). Оба канала пишут в одну таблицу aria_bookings.

## Пользователи
- **Клиент салона** — открывает Mini App по кнопке в боте или прямой ссылке.
  Авторизуется через Telegram.WebApp.initData (без отдельного логина).
- **Владелец** — не взаимодействует с Mini App напрямую,
  получает уведомление (тот же механизм, что и в Sprint 002).

## Scope (IN)

### Часть A — miniapp/ (frontend)
1. Создать папку miniapp/ в репо
2. Файлы: index.html, booking.html, confirm.html, style.css, app.js
3. Telegram.WebApp.js подключается из CDN Telegram
4. initData передаётся в каждый API-запрос как заголовок X-Telegram-Init-Data
5. Booking flow: выбор категории → услуги → даты → времени →
   форма (имя + телефон) → подтверждение → success screen

### Часть B — API endpoints
⚠️ АРХИТЕКТУРНОЕ РЕШЕНИЕ ТРЕБУЕТСЯ: server.py является Flask-приложением
   без доступа к asyncpg pool. Blueprint предполагал aiohttp.
   Выбор реализации API отложен до решения архитектора.
   См. STRUCTURAL_FINDING ниже.

### Часть C — уведомление владельцу
Реализовано через aria/services/notifications.py (создан в этом спринте).
client_booking.py рефакторирован для использования notify_owner().

## STRUCTURAL_FINDING — server.py не aiohttp
Реальная структура:
- web process:    gunicorn server:app (Flask, маркетинговый сайт, нет asyncpg)
- worker process: python -m aria.main (asyncio polling, есть asyncpg pool и боты)

Варианты для API (на выбор архитектора):
A) Flask + psycopg2 синхронно в server.py (нужен psycopg2 в requirements)
B) aiohttp web app внутри aria/main.py (новый asyncio task рядом с polling)
C) Отдельный aria/api.py как третий Railway process (worker2)

Рекомендация Builder: вариант B — наименьший overhead, доступ к pool и runtime.bots.

## Scope (OUT)
- GCal-синхронизация (Sprint 05)
- is_active фильтрация (TD-001, Sprint 004)
- Проверка конфликтов слотов (TD-002, Sprint 005)
- Платежи
- Деплой Mini App на отдельный домен
