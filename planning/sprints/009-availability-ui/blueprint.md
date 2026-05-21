# Sprint 009 — Blueprint

## Reading Order for Builder
1. docs/STATE.md
2. docs/DOMAIN.md — aria_availability (поля, constraint),
   aria_tenants (open_hour, close_hour, slot_minutes, timezone)
3. planning/sprints/009-availability-ui/requirements.md
4. aria/handlers/masters.py — паттерн FSM и callback flow (Sprint 008)
5. aria/handlers/menu.py — паттерн cfg: хендлеров
6. aria/db/repo.py — Masters секция, паттерн CRUD
7. aria/main.py — где регистрировать новый роутер

## Callback Data Map

```
cfg:avail:{id}            → главный экран расписания мастера
cfg:avail_close:{id}      → FSM: выбрать дату → закрыть день
cfg:avail_hours:{id}      → FSM: выбрать дату → ввести часы
cfg:avail_slot:{id}       → FSM: выбрать дату → выбрать слот → заблокировать
cfg:avail_list:{id}       → список существующих блокировок
cfg:avail_del:{avail_id}  → удалить блокировку (разблокировать)
```

## Change 1 — Кнопка в masters.py

В `_masters_text_and_kb()` добавить для каждого мастера кнопку:
`[📅 Расписание]` → `callback_data=f"cfg:avail:{master_id}"`

## Change 2 — aria/handlers/availability.py (новый файл)

### 2a. Главный экран (cfg:avail:{id})

```
📅 Расписание — Иван Иванов

[🔴 Закрыть день]
[🕐 Изменить часы]
[⛔ Заблокировать слот]
[📋 Существующие блокировки]
[← Назад к мастерам]
```

### 2b. FSM: Закрыть день (cfg:avail_close:{id})

```
State 1: waiting_date
  Бот: "Введите дату (ДД.ММ.ГГГГ):"
  Валидация: дата не в прошлом

State 2: confirm
  Бот: "Закрыть {date} для {master_name}?"
  [✅ Да] → INSERT aria_availability (date, is_open=FALSE)
  [❌ Отмена] → главный экран
```

### 2c. FSM: Изменить часы (cfg:avail_hours:{id})

```
State 1: waiting_date
  Бот: "Введите дату (ДД.ММ.ГГГГ):"

State 2: waiting_hours
  Бот: "Введите часы работы (например: 12-18):"
  Парсинг: "12-18" → time_from=12:00, time_to=18:00
  Валидация: from < to, в пределах 0-23

State 3: confirm
  Бот: "Установить {date}: {from}-{to} для {master_name}?"
  [✅ Да] → INSERT aria_availability (date, is_open=TRUE, time_from, time_to)
  [❌ Отмена] → главный экран
```

### 2d. FSM: Заблокировать слот (cfg:avail_slot:{id})

```
State 1: waiting_date
  Бот: "Введите дату (ДД.ММ.ГГГГ):"

State 2: waiting_time
  Бот: "Введите время слота (например: 14:00):"
  Парсинг: "14:00" → time_from=14:00
  time_to = time_from + slot_minutes (из aria_tenants)
  Валидация: время в пределах рабочих часов тенанта

State 3: confirm
  Бот: "Заблокировать слот {time} {date} для {master_name}?"
  [✅ Да] → INSERT aria_availability (date, is_open=FALSE, time_from, time_to)
  [❌ Отмена] → главный экран
```

### 2e. Список блокировок (cfg:avail_list:{id})

```
Показать все записи aria_availability для этого мастера
где date >= TODAY, отсортированные по date ASC.

Формат каждой записи:
  📅 25.05.2026 — 🔴 Закрыт весь день
  📅 26.05.2026 — 🕐 12:00–18:00
  📅 27.05.2026 — ⛔ 14:00–15:00

Кнопка [🗑 Удалить] → cfg:avail_del:{avail_id}
[← Назад] → cfg:avail:{master_id}
```

### 2f. Удалить блокировку (cfg:avail_del:{avail_id})

```
DELETE FROM aria_availability WHERE id={avail_id}
Показать обновлённый список
```

## Change 3 — repo.py CRUD для aria_availability

```python
async def create_availability(
    tenant_id: int,
    master_id: int,
    date: datetime.date,
    is_open: bool,
    time_from: Optional[datetime.time] = None,
    time_to: Optional[datetime.time] = None,
    note: Optional[str] = None,
) -> int:  # возвращает id

async def get_availability(
    master_id: int,
    from_date: Optional[datetime.date] = None,  # default: today
) -> list[asyncpg.Record]:

async def delete_availability(avail_id: int) -> None:

async def get_tenant_slot_minutes(tenant_id: int) -> int:
    # SELECT slot_minutes FROM aria_tenants WHERE id=$1
```

Использовать паттерн `async with _p().acquire() as conn`.

## Change 4 — Регистрация роутера

Добавить `availability_router` в `_build_dispatcher()` в main.py
в том же месте где `masters_router`.

## Files to Create

| Файл | Описание |
|---|---|
| aria/handlers/availability.py | Все хендлеры availability flow |

## Files to Modify

| Файл | Изменение |
|---|---|
| aria/handlers/masters.py | Кнопка 📅 Расписание в списке мастеров |
| aria/db/repo.py | 4 новые CRUD функции |
| aria/main.py | Регистрация availability_router |

## Files NOT to Touch
- miniapp/
- server.py — /api/slots не трогать
- aria/services/scheduler.py
- aria/handlers/client_bot.py
