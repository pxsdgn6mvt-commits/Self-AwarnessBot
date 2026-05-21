# Sprint 007 — DB Schema: Masters (S3-A)

## Goal
Создать DB схему для мульти-мастер функциональности.
Только миграция и минимальная инфраструктура — никакого UI,
никакой бизнес-логики. Все последующие S3 спринты зависят от этой схемы.

## Business Objectives
- Салон может иметь несколько мастеров
- Владелец салона тоже является мастером (основной случай)
- Каждый мастер имеет свои услуги и расписание
- Существующие записи не ломаются

## Decisions
- Владелец = мастер: при создании тенанта автоматически создаётся
  запись мастера для владельца
- aria_availability — только переопределения поверх aria_tenants
  (базовое расписание остаётся в aria_tenants)
- master_id в aria_bookings — опциональный на этом этапе (NULL allowed)
  чтобы не ломать существующие записи

## Inputs
- Существующие таблицы: aria_tenants, aria_bookings, aria_service_items
- working_days, open_hour, close_hour, slot_minutes — уже в aria_tenants
- client_tg_id — уже есть в aria_bookings

## Outputs
- SQL миграция: 3 новые таблицы + 1 ALTER TABLE
- aria/db/migrations/007_masters_schema.sql
- aria/db/repo.py — CRUD функции для aria_masters
- При старте — ensure_owner_master для каждого активного тенанта

## Out of Scope
- Никакого UI (это S3-C)
- Никакой логики доступности (это S3-B)
- Никаких изменений в /api/slots (это S3-B)
- Никаких изменений в Mini App (это S3-D)
- Не писать тесты в этом спринте
