# Sprint 005 — Acceptance Criteria

## Must Pass
- [ ] `tests/` директория существует в корне репо
- [ ] `tests/conftest.py` существует
- [ ] `tests/test_notify_admin.py` существует с 3 тестами
- [ ] `tests/test_watch_tenants.py` существует с 2 тестами
- [ ] `tests/test_api_services.py` существует с 1 тестом
- [ ] pytest, pytest-asyncio, pytest-mock есть в requirements.txt
- [ ] `pytest tests/` завершается без ошибок (все тесты green)
- [ ] Ни один тест не использует реальную БД или реальный Telegram API

## Should Pass
- [ ] test_notify_admin использует реальные env var names из notify_admin.py
- [ ] test_watch_tenants содержит реальную логику (не pass-заглушки)
- [ ] test_api_services проверяет наличие поля working_days в ответе

## NOT Checked
- Coverage процент
- Тесты для miniapp/
- CI/CD интеграция
