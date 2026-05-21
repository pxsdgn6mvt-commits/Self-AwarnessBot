# Sprint 005 — Test Foundation

## Goal
Создать тестовую инфраструктуру с нуля и написать первые unit-тесты
для трёх критических компонентов. После спринта проект имеет работающий
`pytest` и минимальное покрытие ключевых путей.

## Business Objectives
- Регрессии в notify_admin, email resurrection и API обнаруживаются
  автоматически до деплоя
- Любой разработчик может запустить `pytest` и получить результат

## Inputs
- aria/utils/notify_admin.py — готов, нет внешних зависимостей
- aria/main.py — _watch_tenants с email resurrection (Sprint 003)
- server.py — /api/services с working_days (Sprint 002)
- Нет тестовой БД — всё через unittest.mock

## Outputs
- tests/ директория в корне репо
- tests/conftest.py — базовые фикстуры
- tests/test_notify_admin.py
- tests/test_watch_tenants.py
- tests/test_api_services.py
- pytest + pytest-asyncio + pytest-mock добавлены в requirements.txt
- Все тесты проходят через `pytest tests/`

## Out of Scope
- Интеграционные тесты с реальной БД
- Тесты aiogram хендлеров
- Coverage reporting
- CI/CD pipeline
- Тесты для miniapp/
