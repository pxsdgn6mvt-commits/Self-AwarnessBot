# AIBeautyKit — Handoff для нового чата

## Сайт
https://aibeautykit-production.up.railway.app
Репо: pxsdgn6mvt-commits/Self-AwarnessBot, ветка main
Папка: /home/user/Self-AwarnessBot

## Стек
HTML/CSS/JS лендинг. Flask (server.py) на Railway. Procfile: `web: python server.py`

## Что работает
- Сервер запущен (Flask на порту 8080)
- Formspree форма аудита (ID: mjglzlaa) — отправляет email
- Чат-виджет (Claude API через /api/chat) — нужен ANTHROPIC_API_KEY в Railway Variables

## ПРОБЛЕМА — кнопки Stripe не работают

Кнопки "Начать" в секции Pricing не открывают Stripe.
Клик либо ничего не делает, либо скроллит на #audit.

Stripe-ссылки в index.html (строки 484, 505, 524):
- Starter €49:  https://buy.stripe.com/9B6cN5bAP96814ScWlgYU01
- Pro €89:      https://buy.stripe.com/eVqeVd9sHeqsfZM5tTgYU02
- Agency €149:  https://buy.stripe.com/28E9AT34jdmobJw9K9gYU00

Уже попробовали и не помогло:
1. Убрали target="_blank"
2. Добавили JS: window.location.assign(href) с e.preventDefault + e.stopPropagation

## Что проверить

1. Открыть одну ссылку напрямую в браузере — работает ли сам Stripe?
   https://buy.stripe.com/9B6cN5bAP96814ScWlgYU01

2. В Stripe Dashboard проверить:
   - Payment Links -> статус (Active или Restricted?)
   - Аккаунт активирован? (заполнены банковские данные?)
   - Тестовый режим включён? (Test mode вверху Dashboard)

3. Если Stripe ссылки рабочие — смотреть index.html на наличие
   CSS/JS блокировки (pointer-events, z-index, overlapping elements)

## Ключевые файлы
- index.html       — лендинг (849 строк)
- server.py        — Flask + /api/chat
- thank-you.html   — страница после оплаты
- aria_bot.py      — Telegram-бот Aria (Claude API)
- railway.toml     — startCommand = "python server.py"
