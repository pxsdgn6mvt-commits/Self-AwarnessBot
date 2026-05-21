# Acceptance Criteria — Sprint 003

## AC-1: miniapp/ структура
- [x] Папка miniapp/ существует в репо с 5 файлами
- [x] index.html подключает Telegram.WebApp.js из официального CDN
- [x] style.css использует CSS-переменные --tg-theme-* для цветов

## AC-2: API маршруты
- [ ] GET /api/{bot_token}/categories возвращает JSON список категорий
- [ ] GET /api/{bot_token}/services/{cat} возвращает JSON список услуг
- [ ] GET /api/{bot_token}/slots/{date} возвращает JSON список слотов
- [ ] POST /api/{bot_token}/booking создаёт запись в aria_bookings
- [ ] Существующий webhook маршрут в server.py не сломан
  ⚠️ БЛОКЕР: архитектурное решение по API layer (см. requirements.md)

## AC-3: Авторизация
- [ ] POST /api/.../booking без X-Telegram-Init-Data → 401
- [ ] POST с невалидным initData → 401
- [ ] Валидация через HMAC реализована согласно официальной документации Telegram
  ⚠️ БЛОКЕР: зависит от AC-2

## AC-4: notify_owner рефактор
- [x] aria/services/notifications.py создан с notify_owner()
- [x] aria/handlers/client_booking.py импортирует notify_owner оттуда
- [x] Дублирования notify-логики нет

## AC-5: Booking flow в Mini App (happy path)
- [x] Frontend flow реализован: категория → услуга → дата → время → форма → success
- [ ] POST /booking → запись в aria_bookings (зависит от AC-2)
- [ ] Owner получает уведомление (зависит от AC-2)

## AC-6: Регрессия
- [x] aria/handlers/client_booking.py — синтаксис OK
- [x] aria/services/notifications.py — синтаксис OK
- [ ] server.py запускается без ошибок — НЕ ИЗМЕНЁН (существующие маршруты сохранены)
- [x] Bot polling не сломан
