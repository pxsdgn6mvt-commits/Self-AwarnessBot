# Sprint 008 — Masters Admin UI (S3-C)

## Goal
Добавить раздел "Мастера" в owner-бот Settings.
Владелец может видеть список мастеров, добавлять новых,
деактивировать и реактивировать существующих.

## Business Objectives
- Владелец управляет составом мастеров прямо из Telegram
- Без UI мастера существуют только в БД, недостижимы для владельца
- Этот спринт разблокирует S3-D (выбор мастера в Mini App)

## Users Affected
- Владелец салона (единственный пользователь этого UI)

## Inputs
- aria_masters CRUD функции из repo.py (Sprint 007)
- _owner_settings_kb() в menu.py — точка вставки кнопки
- Паттерн callback_data: cfg:xxx, adm:xxx, menu:xxx
- FSM паттерн из существующих хендлеров

## Callback Data Map
- cfg:masters         → список мастеров + кнопки действий
- cfg:master_add      → FSM: имя → телефон → создать
- cfg:master_off:{id} → деактивировать (confirm inline)
- cfg:master_on:{id}  → реактивировать
- menu:settings       → назад в Settings

## Out of Scope
- Редактирование имени/телефона существующего мастера
- Привязка услуг к мастеру (S3-D)
- Команда /masters — только inline flow
- Изменения в miniapp/, server.py
