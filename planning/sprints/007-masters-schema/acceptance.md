# Sprint 007 — Acceptance Criteria

## Must Pass
- [ ] aria/db/migrations/007_masters_schema.sql существует
- [ ] SQL содержит CREATE TABLE aria_masters
- [ ] SQL содержит CREATE TABLE aria_master_services
- [ ] SQL содержит CREATE TABLE aria_availability
- [ ] SQL содержит ALTER TABLE aria_bookings ADD COLUMN master_id
- [ ] Все FK с ON DELETE CASCADE / SET NULL прописаны корректно
- [ ] CONSTRAINT chk_date_or_weekday присутствует в aria_availability
- [ ] aria/db/repo.py содержит create_master()
- [ ] aria/db/repo.py содержит get_masters()
- [ ] aria/db/repo.py содержит get_owner_master()
- [ ] aria/db/repo.py содержит ensure_owner_master()
- [ ] ensure_owner_master() idempotent — повторный вызов не создаёт дубль
- [ ] aria/main.py вызывает ensure_owner_master для активных тенантов
- [ ] docs/DOMAIN.md обновлён с новыми таблицами

## Should Pass
- [ ] Существующие записи в aria_bookings не затронуты (master_id = NULL)
- [ ] IF NOT EXISTS во всех CREATE TABLE
- [ ] ADD COLUMN IF NOT EXISTS в ALTER TABLE

## NOT Checked
- Реальное применение миграции на проде (ручной шаг)
- UI для мастеров (S3-C)
- Логика /api/slots (S3-B)
