# Sprint 010 — Acceptance Criteria

## Functional

| # | Сценарий | Ожидаемый результат |
|---|---|---|
| 1 | Нет записей в availability + master=X | Стандартные слоты (как сейчас) |
| 2 | is_open=FALSE, time_from=NULL (закрытый день) + master=X | `[]` |
| 3 | is_open=TRUE, time_from=08:00, time_to=14:00 (кастомные часы) + master=X | Слоты только 08–14 |
| 4 | is_open=FALSE, time_from=10:00 (заблокированный слот) + master=X | Слот 10:00 отсутствует |
| 5 | is_open=FALSE (день) + is_open=TRUE (часы) одновременно + master=X | `[]` (закрытый день выигрывает) |
| 6 | is_open=FALSE (слот) + is_open=TRUE (часы) одновременно + master=X | Кастомные часы, слот удалён |
| 7 | Без параметра master= | Поведение идентично текущему (aria_availability не читается) |
| 8 | working_days исключает дату | `[]` (до чтения availability) |

## Code
- `_apply_availability()` — отдельная функция в server.py
- SQL для availability inline (не через repo.py async)
- Параметр `master` принимается, тип int, опциональный
- Нет изменений в формате ответа

## Non-regression
- Без `master=` параметра — нет обращений к aria_availability
