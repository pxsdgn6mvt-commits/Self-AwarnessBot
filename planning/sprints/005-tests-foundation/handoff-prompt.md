# Sprint 005 Handoff — Builder Instructions

## Read First (обязательно, в этом порядке)
1. `docs/STATE.md`
2. `planning/sprints/005-tests-foundation/requirements.md`
3. `planning/sprints/005-tests-foundation/blueprint.md`
4. `planning/sprints/005-tests-foundation/acceptance.md`

## Then Read Source Files
5. `aria/utils/notify_admin.py` — полностью, зафиксировать env var names
6. `aria/main.py` — найти `_watch_tenants`, зафиксировать сигнатуру
7. `aria/services/scheduler.py` — найти `start_email_job`, зафиксировать сигнатуру
8. `server.py` — найти `/api/services`, зафиксировать структуру ответа

## Execute

### Step 1 — requirements.txt
Добавить: `pytest>=8.0`, `pytest-asyncio>=0.23`, `pytest-mock>=3.12`

### Step 2 — Создать структуру
`tests/__init__.py` (пустой), `tests/conftest.py`

### Step 3–5 — Написать тесты
Прочитать исходники, написать рабочие тесты с моками. НЕ оставлять pass-заглушки.

### Step 6 — Запустить тесты
`pytest tests/ -v` — убедиться что все green до написания summary.

## Constraints
- НЕ модифицировать `aria/` исходники
- НЕ использовать реальную БД или Telegram API
- Если `_watch_tenants` сложно изолировать — описать в Assumptions

## Completion Summary Format
```
Files Created / Files Modified / Test Results (pytest -v output)
Env Vars in notify_admin.py / Assumptions / Acceptance Criteria / Ready for Sprint 006
```
