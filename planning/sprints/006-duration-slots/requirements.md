# Sprint 006 — Duration-aware Slot Blocking (TD-003)
Статус: ACTIVE
Дата: 2026-05-21

## Проблема

TD-003: бронь блокирует только 1 слот независимо от duration_minutes услуги.
Пример: услуга 90 мин, slot_minutes=60 → должна блокировать 2 слота,
но сейчас блокирует только 1. Клиент может записаться в перекрывающееся время.

## Scope IN

1. repo.get_slots_on_date() — возвращать (start_datetime, duration_minutes)
   LEFT JOIN aria_service_items по названию услуги
   Fallback: COALESCE(si.duration_minutes, t.slot_minutes)

2. Shared util slots_overlap(slot_start_min, slot_min, bookings) → bool
   Логика: booked_start < slot_end AND booked_end > slot_start
   Определить в repo.py, импортировать в quick.py и main.py

3. quick.py _time_kb — заменить set-exclusion на overlap check

4. aria/main.py _handle_slots — заменить inline set-exclusion
   использовать repo.get_slots_on_date + repo.slots_overlap

## Scope OUT

- Изменение схемы aria_bookings (не добавляем service_item_id)
- GCal sync
- Отмена броней клиентом

## Входные данные

- aria_bookings: tenant_id, scheduled_at, service (text), status
- aria_service_items: name, duration_minutes
- aria_tenants: slot_minutes (fallback duration), timezone
