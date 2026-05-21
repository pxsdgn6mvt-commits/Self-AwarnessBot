# Sprint 010 — Requirements: /api/slots + Availability

## Business Goal
Слоты, возвращаемые Mini App, должны учитывать расписание мастеров
(закрытые дни, изменённые часы, заблокированные слоты), созданное в Sprint 009.

## Users
- Клиент салона (через Mini App) — видит только реально доступные слоты
- Владелец салона — знает, что блокировки из бота работают

## Scope

### IN
1. Добавить опциональный параметр `?master=X` в GET /api/slots
2. Читать aria_availability для заданного tenant_id + master_id + date
3. Применить правила фильтрации (см. ниже)
4. Обратная совместимость: без `?master=X` логика не ломается

### OUT
- UI изменения в Mini App (Sprint 012)
- Множественный выбор мастеров
- Изменение схемы aria_availability

## Priority Rules (DECISION)
Приоритет применяется в порядке убывания:

1. `is_open=FALSE, time_from IS NOT NULL` → блокировка слота
   Удаляет конкретный слот. Выигрывает над всем.

2. `is_open=FALSE, time_from IS NULL` → закрытый день
   Возвращает []. Игнорирует изменённые часы.

3. `is_open=TRUE, time_from IS NOT NULL` → изменённые часы дня
   Заменяет open_hour/close_hour из aria_tenants на кастомные.

4. Нет записей в aria_availability → стандартная логика (текущий код).

## Inputs / Outputs
Input:  `GET /api/slots?tenant_id=X&date=YYYY-MM-DD[&master=Y]`
Output: `["10:00", "11:00", ...]` или `[]`
