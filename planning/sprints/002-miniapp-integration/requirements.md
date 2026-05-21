# Sprint 002 — Mini App End-to-End Integration (S2-C)

## Goal
Замкнуть интеграцию Mini App с ботом. После спринта клиент должен получить
кнопку в боте, открыть Mini App, выбрать услугу/дату/время и создать запись
— без ручного ввода URL и без пустых экранов.

## Business Objectives
- Клиент открывает Mini App одним тапом прямо из Telegram-бота
- Mini App корректно обращается к Railway backend по абсолютному URL
- DateScreen не показывает нерабочие дни тенанта

## Users Affected
- Конечный клиент салона (основной пользователь Mini App)
- Владелец салона (его тенант должен корректно передаваться)

## Inputs
- MINIAPP_URL — уже есть в .env.example, надо использовать
- tenant.id — доступен в контексте любого хендлера через get_tenant()
- working_days — поле тенанта в БД (тип: список дней или bitmask,
  уточнить из DOMAIN.md / development.md)

## Outputs
- Новый или изменённый хендлер в aria/ с WebApp-кнопкой
- Изменённый /api/services или новый поле в ответе для working_days
- Изменённый DateScreen.tsx с фильтрацией нерабочих дней
- Инструкция для ручного шага: пересборка Cloudflare Pages с env-переменной

## Out of Scope
- Не трогать APScheduler, email-джобы, reminder-логику
- Не добавлять тесты
- Не менять схему БД (только читать working_days)
- Не менять _tg_notify() и логику уведомлений
