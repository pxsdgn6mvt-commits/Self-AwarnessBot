# Sprint 009 — Availability UI в owner-боте (S3-B part 1)

## Goal
Владелец салона может управлять расписанием каждого мастера
прямо из Telegram: закрыть день целиком, задать другие часы
на конкретный день, заблокировать конкретный слот.
Данные пишутся в aria_availability. /api/slots не меняется в этом спринте.

## Business Objectives
- Владелец закрывает отпуск мастера в несколько тапов
- Владелец блокирует конкретный слот (личные дела мастера)
- Данные готовы для Sprint 010 где /api/slots начнёт их читать

## Users Affected
- Владелец салона (единственный пользователь этого UI сейчас)
- Мастер-бот получит аналогичный UI в Sprint 011

## Three Action Types
1. Закрыть день целиком (date, is_open=FALSE, time_from=NULL, time_to=NULL)
2. Изменить часы на день (date, is_open=TRUE, time_from=X, time_to=Y)
3. Заблокировать слот (date, is_open=FALSE, time_from=X, time_to=X+slot)

## Inputs
- aria_availability таблица (Sprint 007)
- aria_masters CRUD из repo.py (Sprint 007-008)
- Паттерн cfg: хендлеров из masters.py (Sprint 008)
- open_hour, close_hour, slot_minutes из aria_tenants

## Outputs
- aria/handlers/availability.py — новый файл
- repo.py — CRUD для aria_availability
- menu.py — кнопка 📅 Расписание в карточке мастера
- Данные в aria_availability готовы для Sprint 010

## Out of Scope
- /api/slots не меняется (Sprint 010)
- Master-bot UI (Sprint 011)
- miniapp/ не трогать
