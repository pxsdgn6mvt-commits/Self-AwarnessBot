# Sprint 004 — is_active Filtering (TD-001)
Статус: ACTIVE
Дата: 2026-05-21

## Проблема

TD-001: колонок is_active нет в aria_service_categories и aria_service_items.
Клиент видит все услуги, включая те, что владелец хочет скрыть.
API и FSM показывают всё без фильтрации.

## Scope IN

1. БД-миграция:
   ALTER TABLE aria_service_categories ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true
   ALTER TABLE aria_service_items ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true

2. Фильтрация в API (aria/main.py):
   _handle_categories: WHERE is_active = true
   _handle_services:   WHERE is_active = true

3. Фильтрация в client booking FSM (aria/handlers/client_booking.py):
   choosing_category: WHERE is_active = true
   choosing_service:  WHERE is_active = true

4. Owner UI: владелец может скрывать/показывать категорию или услугу.
   Минимум: команда /toggle_service <id> или кнопка в существующем setup flow.
   Уточнить по dry run: что уже есть в setup.py.

## Scope OUT

- Удаление категорий/услуг (отдельная задача)
- Конфликты слотов (TD-002)
- Любые другие таблицы

## Входные данные

- aria/main.py — _handle_categories, _handle_services
- aria/handlers/client_booking.py — choosing_category, choosing_service
- aria/handlers/setup.py — существующий owner UI для услуг
- aria/db/models.py — паттерн миграции
