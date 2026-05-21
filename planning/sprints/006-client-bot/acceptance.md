# Sprint 006 — Acceptance Criteria

## Must Pass
- [ ] aria/handlers/client_bot.py существует
- [ ] /start хендлер извлекает tenant_id из deep link (формат: tenant_123)
- [ ] /start хендлер возвращает WebApp кнопку с правильным URL
- [ ] Если tenant_id отсутствует — возвращает понятное сообщение
- [ ] aria/main.py инициализирует client_bot если CLIENT_BOT_TOKEN задан
- [ ] Если CLIENT_BOT_TOKEN не задан — owner-боты продолжают работать
- [ ] server.py сохраняет client_tg_id в aria_bookings при бронировании
- [ ] server.py отправляет уведомление мастеру после бронирования
- [ ] .env.example содержит CLIENT_BOT_TOKEN с комментарием

## Should Pass
- [ ] Уведомление мастеру содержит: имя клиента, услугу, дату, время
- [ ] client_tg_id опциональный — бронирование работает и без него
- [ ] Graceful degradation если CLIENT_BOT_TOKEN не задан

## Manual Steps (не проверять автоматически)
- Создать бота в BotFather → получить CLIENT_BOT_TOKEN
- Добавить CLIENT_BOT_TOKEN в Railway env vars
- Выставить VITE_API_BASE в Cloudflare Pages (из Sprint 002)
- Проверить есть ли колонка client_tg_id в aria_bookings (из summary)
