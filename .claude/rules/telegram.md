# Telegram / aiogram Rules for Aria

- aiogram 3.x only — no aiogram 2.x patterns
- New routers: register in main.py _build_dispatcher(), BEFORE chat.router (catch-all)
- FSM states: store as "Group:name" string — never str(state) with angle brackets
- Inline keyboards: use InlineKeyboardBuilder
- Reply keyboards: use ReplyKeyboardMarkup
- Always answer callbacks: await callback.answer() to remove loading spinner
- ParseMode.HTML is default (set in DefaultBotProperties)
- Mini App initData MUST be validated with HMAC-SHA256 using bot token before trusting
- Never expose bot tokens in logs or responses
