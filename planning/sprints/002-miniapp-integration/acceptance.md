# Sprint 002 — Acceptance Criteria

## Must Pass (блокирующие)

- [ ] В `aria/` есть код формирующий `WebAppInfo`-кнопку с URL
      вида `f"{MINIAPP_URL}?tenant_id={tenant.id}"`
- [ ] `MINIAPP_URL` читается из `os.getenv()`, не захардкожен
- [ ] `/api/services` возвращает поле `working_days` в JSON
- [ ] `DateScreen.tsx` содержит логику фильтрации нерабочих дней
- [ ] Фильтр в DateScreen использует `working_days` из ответа API,
      не захардкоженный список

## Should Pass (важные)

- [ ] Существующие хендлеры `/start` или меню не сломаны
      (логика до кнопки не изменена)
- [ ] `/api/services` не сломан для существующих клиентов
      (`working_days` добавлен, остальные поля не тронуты)
- [ ] В summary Builder'а явно написан manual step для Cloudflare

## Out of Scope (не проверять)

- Работу Mini App end-to-end на проде (требует ручного деплоя)
- APScheduler, email-джобы, тесты
