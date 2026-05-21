# Sprint 005 — Blueprint

## Reading Order for Builder
1. `docs/STATE.md`
2. `planning/sprints/005-tests-foundation/requirements.md`
3. `aria/utils/notify_admin.py` — понять что тестируем
4. `aria/main.py` — найти `_watch_tenants`, зависимости
5. `server.py` — найти `/api/services`, структура ответа
6. `requirements.txt` (корневой) — куда добавлять зависимости

## Change 1 — requirements.txt
```
pytest>=8.0
pytest-asyncio>=0.23
pytest-mock>=3.12
```

## Change 2 — tests/conftest.py
Минимальный conftest с event_loop фикстурой для asyncio тестов.

## Change 3 — tests/test_notify_admin.py
3 теста: успешная отправка, отсутствие env vars, Telegram недоступен.

## Change 4 — tests/test_watch_tenants.py
2 теста: джоб отсутствует → start_email_job вызван; джоб существует → не вызван.

## Change 5 — tests/test_api_services.py
1 тест: /api/services возвращает working_days в ответе.

## Files to Create
| Файл | Описание |
|---|---|
| `tests/__init__.py` | Пустой |
| `tests/conftest.py` | event_loop фикстура |
| `tests/test_notify_admin.py` | 3 теста |
| `tests/test_watch_tenants.py` | 2 теста |
| `tests/test_api_services.py` | 1 тест |

## Files to Modify
| Файл | Изменение |
|---|---|
| `requirements.txt` | Добавить pytest, pytest-asyncio, pytest-mock |

## Files NOT to Touch
- `aria/` исходники
- `miniapp/`
- `server.py` исходники
- Схема БД
