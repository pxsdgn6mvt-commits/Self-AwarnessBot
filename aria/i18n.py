"""Owner-facing UI translations — Russian, English, Finnish."""
from __future__ import annotations

# ── Month / day name arrays ───────────────────────────────────────────────────

MON_SHORT: dict[str, list[str]] = {
    "ru": ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"],
    "en": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
    "fi": ["tammi","helmi","maalis","huhti","touko","kesä","heinä","elo","syys","loka","marras","joulu"],
}

MON_GENITIVE: dict[str, list[str]] = {
    "ru": ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"],
    "en": ["January","February","March","April","May","June","July","August","September","October","November","December"],
    "fi": ["tammikuuta","helmikuuta","maaliskuuta","huhtikuuta","toukokuuta","kesäkuuta","heinäkuuta","elokuuta","syyskuuta","lokakuuta","marraskuuta","joulukuuta"],
}

MON_FULL: dict[str, list[str]] = {
    "ru": ["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"],
    "en": ["January","February","March","April","May","June","July","August","September","October","November","December"],
    "fi": ["Tammikuu","Helmikuu","Maaliskuu","Huhtikuu","Toukokuu","Kesäkuu","Heinäkuu","Elokuu","Syyskuu","Lokakuu","Marraskuu","Joulukuu"],
}

DAY_SHORT: dict[str, list[str]] = {
    "ru": ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"],
    "en": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
    "fi": ["Ma","Ti","Ke","To","Pe","La","Su"],
}

DAY_FULL: dict[str, list[str]] = {
    "ru": ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"],
    "en": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
    "fi": ["Maanantai","Tiistai","Keskiviikko","Torstai","Perjantai","Lauantai","Sunnuntai"],
}


def fmt_date(day: int, month_idx: int, lang: str) -> str:
    """Format a day/month as '5 мая' (ru), 'May 5' (en), '5. toukokuuta' (fi)."""
    m = MON_GENITIVE.get(lang, MON_GENITIVE["ru"])[month_idx]
    if lang == "en":
        return f"{m} {day}"
    if lang == "fi":
        return f"{day}. {m}"
    return f"{day} {m}"


# ── Translation table ─────────────────────────────────────────────────────────

T: dict[str, dict[str, str]] = {
    # ── Main keyboard buttons ─────────────────────────────────────────────────
    "btn_today":      {"ru": "📅 Сегодня",       "en": "📅 Today",       "fi": "📅 Tänään"},
    "btn_tomorrow":   {"ru": "📅 Завтра",         "en": "📅 Tomorrow",    "fi": "📅 Huomenna"},
    "btn_new":        {"ru": "➕ Новая запись",   "en": "➕ New booking", "fi": "➕ Uusi varaus"},
    "btn_upcoming":   {"ru": "📋 Ближайшие",      "en": "📋 Upcoming",    "fi": "📋 Tulevat"},
    "btn_dashboard":  {"ru": "📊 Дашборд",        "en": "📊 Dashboard",   "fi": "📊 Kojelauta"},
    "btn_settings":   {"ru": "⚙️ Настройки",      "en": "⚙️ Settings",    "fi": "⚙️ Asetukset"},

    # ── Day labels ────────────────────────────────────────────────────────────
    "lbl_today":      {"ru": "Сегодня",  "en": "Today",    "fi": "Tänään"},
    "lbl_tomorrow":   {"ru": "Завтра",   "en": "Tomorrow", "fi": "Huomenna"},
    "this_week":      {"ru": "Эта неделя",      "en": "This week",      "fi": "Tämä viikko"},
    "next_week":      {"ru": "Следующая неделя","en": "Next week",       "fi": "Ensi viikko"},

    # ── Schedule ──────────────────────────────────────────────────────────────
    "no_bookings":    {"ru": "Записей нет.",              "en": "No bookings.",           "fi": "Ei varauksia."},
    "no_upcoming":    {"ru": "Ближайших записей нет.",    "en": "No upcoming bookings.",  "fi": "Ei tulevia varauksia."},
    "upcoming_title": {"ru": "Ближайшие записи",          "en": "Upcoming bookings",      "fi": "Tulevat varaukset"},
    "add_booking":    {"ru": "➕ Добавить запись",        "en": "➕ Add booking",          "fi": "➕ Lisää varaus"},
    "free_day":       {"ru": "свободно",                  "en": "free",                   "fi": "vapaa"},

    # ── Booking card ──────────────────────────────────────────────────────────
    "service_label":  {"ru": "Услуга",         "en": "Service",     "fi": "Palvelu"},
    "arrived_mark":   {"ru": "✅ Пришёл",       "en": "✅ Arrived",  "fi": "✅ Saapui"},
    "noshow_mark":    {"ru": "🚫 Не пришёл",   "en": "🚫 No-show",  "fi": "🚫 Ei saapunut"},
    "paid_mark":      {"ru": "💰 Оплачено ✅",  "en": "💰 Paid ✅",  "fi": "💰 Maksettu ✅"},
    "btn_arrived":    {"ru": "✅ Пришёл",       "en": "✅ Arrived",  "fi": "✅ Saapui"},
    "btn_noshow":     {"ru": "🚫 Не пришёл",   "en": "🚫 No-show",  "fi": "🚫 Ei saapunut"},
    "btn_pay":        {"ru": "💰 Оплата",       "en": "💰 Payment",  "fi": "💰 Maksu"},
    "btn_paid_done":  {"ru": "✅ Оплачено",     "en": "✅ Paid",     "fi": "✅ Maksettu"},
    "btn_reschedule": {"ru": "✏️ Перенести",    "en": "✏️ Reschedule","fi": "✏️ Siirrä"},
    "btn_cancel_bk":  {"ru": "❌ Отменить",     "en": "❌ Cancel",   "fi": "❌ Peruuta"},
    "btn_note":       {"ru": "📝 Заметка",      "en": "📝 Note",     "fi": "📝 Muistiinpano"},
    "btn_back_day":   {"ru": "◀️ К списку дня", "en": "◀️ Back to day","fi": "◀️ Päivän lista"},
    "btn_back":       {"ru": "◀️ Назад",        "en": "◀️ Back",     "fi": "◀️ Takaisin"},
    "btn_cancel_act": {"ru": "❌ Отмена",       "en": "❌ Cancel",   "fi": "❌ Peruuta"},

    # ── Toast notifications ───────────────────────────────────────────────────
    "toast_arrived":   {"ru": "✅ Отмечено — пришёл",    "en": "✅ Marked — arrived",       "fi": "✅ Merkitty — saapui"},
    "toast_noshow":    {"ru": "🚫 Отмечено — не пришёл", "en": "🚫 Marked — no-show",       "fi": "🚫 Merkitty — ei saapunut"},
    "toast_paid":      {"ru": "✅ Оплачено",              "en": "✅ Paid",                   "fi": "✅ Maksettu"},
    "toast_unpaid":    {"ru": "↩️ Оплата отменена",      "en": "↩️ Payment cancelled",      "fi": "↩️ Maksu peruutettu"},
    "toast_cancelled": {"ru": "✅ Запись отменена",       "en": "✅ Booking cancelled",       "fi": "✅ Varaus peruutettu"},
    "no_access":       {"ru": "Нет доступа.",             "en": "No access.",                "fi": "Ei pääsyä."},
    "not_found":       {"ru": "Запись не найдена.",       "en": "Booking not found.",        "fi": "Varausta ei löydy."},
    "not_found_system":{"ru": "Запись не найдена в системе.", "en": "Booking not found in system.", "fi": "Varausta ei löydy järjestelmästä."},
    "already_cancelled":{"ru":"Запись уже отменена или не найдена.", "en":"Booking already cancelled or not found.", "fi":"Varaus on jo peruutettu tai sitä ei löydy."},
    "cancelled_act":   {"ru": "Отменено.",                "en": "Cancelled.",                "fi": "Peruutettu."},

    # ── Dashboard ─────────────────────────────────────────────────────────────
    "dash_day":        {"ru": "📅 День",       "en": "📅 Day",      "fi": "📅 Päivä"},
    "dash_week":       {"ru": "📆 Неделя",     "en": "📆 Week",     "fi": "📆 Viikko"},
    "dash_month":      {"ru": "🗓 Месяц",      "en": "🗓 Month",    "fi": "🗓 Kuukausi"},
    "dash_analytics":  {"ru": "📊 Аналитика",  "en": "📊 Analytics","fi": "📊 Analytiikka"},
    "bookings_count":  {"ru": "📋 Записей",    "en": "📋 Bookings", "fi": "📋 Varaukset"},
    "next_client":     {"ru": "⏰ Следующий",  "en": "⏰ Next",     "fi": "⏰ Seuraava"},
    "no_more_today":   {"ru": "⏰ Записей до конца дня нет", "en": "⏰ No more bookings today", "fi": "⏰ Ei enää varauksia tänään"},
    "free_slots_lbl":  {"ru": "🕐 Свободно",   "en": "🕐 Free",    "fi": "🕐 Vapaana"},
    "no_free_slots":   {"ru": "🔴 Свободных окон нет", "en": "🔴 No free slots", "fi": "🔴 Ei vapaita aikoja"},
    "in_h":            {"ru": "ч",             "en": "h",           "fi": "t"},
    "in_min":          {"ru": "мин",           "en": "min",         "fi": "min"},
    "in_prefix":       {"ru": "через",         "en": "in",          "fi": ""},
    "in_suffix":       {"ru": "",              "en": "",            "fi": " päästä"},
    "per_week":        {"ru": "в неделю",      "en": "per week",    "fi": "viikossa"},
    "income_expected": {"ru": "💰 Ожидается",  "en": "💰 Expected", "fi": "💰 Odotettu"},
    "income_paid":     {"ru": "✅ Оплачено",   "en": "✅ Paid",     "fi": "✅ Maksettu"},
    "avg_check":       {"ru": "💳 Средний чек","en": "💳 Avg. ticket","fi": "💳 Keskim. hinta"},
    "master_share":    {"ru": "👤 Доля",       "en": "👤 Share",    "fi": "👤 Osuus"},
    "net_income":      {"ru": "🧾 Чистыми",    "en": "🧾 Net",      "fi": "🧾 Netto"},
    "back_to_dash":    {"ru": "◀️ Назад к дашборду","en": "◀️ Back to dashboard","fi": "◀️ Takaisin kojelautaan"},

    # ── Analytics ─────────────────────────────────────────────────────────────
    "top_services":    {"ru": "Топ услуги:",       "en": "Top services:",   "fi": "Suosituimmat palvelut:"},
    "top_clients":     {"ru": "Топ клиенты:",      "en": "Top clients:",    "fi": "Parhaat asiakkaat:"},
    "no_data_svc":     {"ru": "Нет данных по услугам",  "en": "No service data", "fi": "Ei palvelutietoja"},
    "no_data_cli":     {"ru": "Нет данных по клиентам", "en": "No client data",  "fi": "Ei asiakastietoja"},
    "risky_clients":   {"ru": "⚠️ Рискованные клиенты:","en": "⚠️ Risky clients:","fi": "⚠️ Riskiasiakkaat:"},
    "noshows_label":   {"ru": "неявок",             "en": "no-shows",        "fi": "ei-saapunut"},
    "cancels_label":   {"ru": "отмен",              "en": "cancellations",   "fi": "peruutusta"},
    "visits_short":    {"ru": "визит",              "en": "visit",           "fi": "käynti"},

    # ── Booking wizard ────────────────────────────────────────────────────────
    "new_booking":     {"ru": "➕ <b>Новая запись</b>",  "en": "➕ <b>New booking</b>", "fi": "➕ <b>Uusi varaus</b>"},
    "choose_cat":      {"ru": "Выбери категорию:",       "en": "Choose category:",      "fi": "Valitse kategoria:"},
    "choose_svc":      {"ru": "Выбери услугу:",          "en": "Choose service:",       "fi": "Valitse palvelu:"},
    "choose_date":     {"ru": "Выбери дату:",            "en": "Choose date:",          "fi": "Valitse päivä:"},
    "choose_time":     {"ru": "Выбери время:",           "en": "Choose time:",          "fi": "Valitse aika:"},
    "client_name_lbl": {"ru": "Имя клиента:",            "en": "Client name:",          "fi": "Asiakkaan nimi:"},
    "cat_label":       {"ru": "Категория",               "en": "Category",              "fi": "Kategoria"},
    "svc_label":       {"ru": "Услуга",                  "en": "Service",               "fi": "Palvelu"},
    "date_label":      {"ru": "Дата",                    "en": "Date",                  "fi": "Päivämäärä"},
    "time_label":      {"ru": "Время",                   "en": "Time",                  "fi": "Aika"},
    "other_date":      {"ru": "📝 Другая дата",         "en": "📝 Other date",          "fi": "📝 Muu päivä"},
    "other_time":      {"ru": "📝 Другое время",        "en": "📝 Other time",          "fi": "📝 Muu aika"},
    "bad_date":        {"ru": "Не понял дату. Попробуй <code>20.05</code>:", "en": "Couldn't parse date. Try <code>20.05</code>:", "fi": "En ymmärtänyt päivää. Kokeile <code>20.05</code>:"},
    "bad_time":        {"ru": "Формат <code>ЧЧ:ММ</code>, например <code>14:30</code>:", "en": "Format <code>HH:MM</code>, e.g. <code>14:30</code>:", "fi": "Muoto <code>HH:MM</code>, esim. <code>14:30</code>:"},
    "booking_fail":    {"ru": "❌ Не удалось разобрать дату/время. Попробуй ещё раз.", "en": "❌ Couldn't parse date/time. Try again.", "fi": "❌ En ymmärtänyt päivää/aikaa. Yritä uudelleen."},

    # ── Note / reschedule ─────────────────────────────────────────────────────
    "enter_note":      {"ru": "📝 Введи заметку для этой записи\n(или /skip чтобы отменить):", "en": "📝 Enter a note for this booking\n(or /skip to cancel):", "fi": "📝 Kirjoita muistiinpano tälle varaukselle\n(tai /skip peruuttaaksesi):"},
    "note_saved":      {"ru": "📝 Заметка сохранена.",  "en": "📝 Note saved.",         "fi": "📝 Muistiinpano tallennettu."},
    "enter_reschedule":{"ru": "✏️ Введи новую дату и время записи\nНапример: <code>20 мая 14:00</code>\nИли /skip чтобы отменить.", "en": "✏️ Enter new date and time\nE.g.: <code>May 20 14:00</code>\nOr /skip to cancel.", "fi": "✏️ Syötä uusi päivä ja aika\nEsim.: <code>20.5. 14:00</code>\nTai /skip peruuttaaksesi."},
    "bad_reschedule":  {"ru": "Не удалось распознать дату. Попробуй ещё раз, например: <code>20 мая 14:00</code>\nИли /skip чтобы отменить.", "en": "Couldn't parse date. Try again, e.g.: <code>May 20 14:00</code>\nOr /skip to cancel.", "fi": "En ymmärtänyt päivää. Yritä uudelleen, esim.: <code>20.5. 14:00</code>\nTai /skip peruuttaaksesi."},

    # ── Settings panel ────────────────────────────────────────────────────────
    "settings_title":     {"ru": "⚙️ <b>Настройки</b>",      "en": "⚙️ <b>Settings</b>",       "fi": "⚙️ <b>Asetukset</b>"},
    "integrations_title": {"ru": "⚙️ <b>Интеграции</b>",     "en": "⚙️ <b>Integrations</b>",   "fi": "⚙️ <b>Integraatiot</b>"},
    "btn_services":       {"ru": "📋 Услуги и категории",     "en": "📋 Services & categories", "fi": "📋 Palvelut ja kategoriat"},
    "btn_clients":        {"ru": "👤 Клиенты",               "en": "👤 Clients",               "fi": "👤 Asiakkaat"},
    "btn_income":         {"ru": "💼 Доходы мастера",        "en": "💼 Master income",         "fi": "💼 Tulot"},
    "btn_reminders":      {"ru": "⏰ Напоминания",            "en": "⏰ Reminders",             "fi": "⏰ Muistutukset"},
    "btn_help":           {"ru": "❓ Помощь",                 "en": "❓ Help",                   "fi": "❓ Ohje"},
    "btn_integrations":   {"ru": "⚙️ Интеграции",            "en": "⚙️ Integrations",          "fi": "⚙️ Integraatiot"},
    "btn_close":          {"ru": "✖️ Закрыть",               "en": "✖️ Close",                 "fi": "✖️ Sulje"},
    "btn_tz":             {"ru": "🕐 Часовой пояс",          "en": "🕐 Timezone",              "fi": "🕐 Aikavyöhyke"},
    "btn_gcal":           {"ru": "📅 Google Calendar",        "en": "📅 Google Calendar",        "fi": "📅 Google Calendar"},
    "btn_email":          {"ru": "📧 Email",                  "en": "📧 Email",                  "fi": "📧 Sähköposti"},
    "btn_status":         {"ru": "📊 Статус",                 "en": "📊 Status",                "fi": "📊 Tila"},
    "btn_reset_hist":     {"ru": "🗑 Сбросить историю",      "en": "🗑 Reset history",          "fi": "🗑 Tyhjennä historia"},
    "btn_lang":           {"ru": "🌐 Язык интерфейса",        "en": "🌐 Interface language",     "fi": "🌐 Käyttöliittymän kieli"},
    "btn_back_settings":  {"ru": "◀️ Назад к настройкам",    "en": "◀️ Back to settings",      "fi": "◀️ Takaisin asetuksiin"},

    # ── Timezone ──────────────────────────────────────────────────────────────
    "tz_title":     {"ru": "🕐 <b>Часовой пояс</b>", "en": "🕐 <b>Timezone</b>", "fi": "🕐 <b>Aikavyöhyke</b>"},
    "tz_current":   {"ru": "Текущий",    "en": "Current",   "fi": "Nykyinen"},
    "tz_choose":    {"ru": "Выбери новый:", "en": "Choose new:", "fi": "Valitse uusi:"},
    "tz_saved":     {"ru": "✅ Часовой пояс:", "en": "✅ Timezone:", "fi": "✅ Aikavyöhyke:"},

    # ── Income settings ───────────────────────────────────────────────────────
    "income_title":      {"ru": "💼 <b>Доходы мастера</b>",    "en": "💼 <b>Master income</b>",   "fi": "💼 <b>Mestarin tulot</b>"},
    "income_desc":       {"ru": "Укажи долю мастера и ставку налога — дашборд покажет чистый заработок.\n\nНажми кнопку чтобы изменить значение:", "en": "Set master share and tax rate — the dashboard will show net earnings.\n\nTap a button to change:", "fi": "Aseta mestarin osuus ja veroaste — kojelauta näyttää nettotulot.\n\nPaina nappia muuttaaksesi:"},
    "master_pct_lbl":    {"ru": "👤 Доля мастера",             "en": "👤 Master share",           "fi": "👤 Mestarin osuus"},
    "master_pct_none":   {"ru": "не задана",                   "en": "not set",                   "fi": "ei asetettu"},
    "tax_lbl":           {"ru": "🧾 Налог",                    "en": "🧾 Tax",                    "fi": "🧾 Vero"},
    "tax_none":          {"ru": "не задан",                    "en": "not set",                   "fi": "ei asetettu"},
    "master_title":      {"ru": "👤 <b>Доля мастера</b>",      "en": "👤 <b>Master share</b>",    "fi": "👤 <b>Mestarin osuus</b>"},
    "master_current":    {"ru": "Текущая",  "en": "Current",   "fi": "Nykyinen"},
    "master_prompt":     {"ru": "Введи процент (например <code>70</code>) или /skip чтобы убрать.", "en": "Enter percentage (e.g. <code>70</code>) or /skip to remove.", "fi": "Syötä prosentti (esim. <code>70</code>) tai /skip poistaaksesi."},
    "master_bad":        {"ru": "Введи число от 1 до 100, например <code>70</code>, или /skip:", "en": "Enter a number from 1 to 100, e.g. <code>70</code>, or /skip:", "fi": "Syötä luku 1–100, esim. <code>70</code>, tai /skip:"},
    "master_deleted":    {"ru": "✅ Доля мастера удалена.",    "en": "✅ Master share removed.",  "fi": "✅ Mestarin osuus poistettu."},
    "master_saved":      {"ru": "✅ Доля мастера:",            "en": "✅ Master share:",           "fi": "✅ Mestarin osuus:"},
    "tax_title":         {"ru": "🧾 <b>Налог</b>",            "en": "🧾 <b>Tax</b>",             "fi": "🧾 <b>Vero</b>"},
    "tax_current":       {"ru": "Текущий",  "en": "Current",   "fi": "Nykyinen"},
    "tax_prompt":        {"ru": "Введи ставку в % (например <code>6</code> для самозанятого, <code>13</code> для НДФЛ)\nИли /skip чтобы убрать.", "en": "Enter rate in % (e.g. <code>6</code> for self-employed, <code>13</code> for income tax)\nOr /skip to remove.", "fi": "Syötä prosentti (esim. <code>6</code> yrittäjälle, <code>13</code> palkansaajalle)\nTai /skip poistaaksesi."},
    "tax_bad":           {"ru": "Введи число от 0 до 99, например <code>6</code>, или /skip:", "en": "Enter a number from 0 to 99, e.g. <code>6</code>, or /skip:", "fi": "Syötä luku 0–99, esim. <code>6</code>, tai /skip:"},
    "tax_deleted":       {"ru": "✅ Налог удалён.",            "en": "✅ Tax removed.",           "fi": "✅ Vero poistettu."},
    "tax_saved":         {"ru": "✅ Налог:",                   "en": "✅ Tax:",                   "fi": "✅ Vero:"},

    # ── Reminders settings ────────────────────────────────────────────────────
    "reminders_title": {"ru": "⏰ <b>Напоминания</b>",                         "en": "⏰ <b>Reminders</b>",                             "fi": "⏰ <b>Muistutukset</b>"},
    "remind_before":   {"ru": "<b>За сколько часов напоминать о записи:</b>",  "en": "<b>How many hours before to remind:</b>",         "fi": "<b>Kuinka monta tuntia ennen muistutus:</b>"},
    "remind_summary":  {"ru": "<b>Когда присылать сводку на завтра:</b>",      "en": "<b>When to send tomorrow's summary:</b>",          "fi": "<b>Milloin lähettää huomisen yhteenveto:</b>"},

    # ── Clients panel ─────────────────────────────────────────────────────────
    "clients_empty":   {"ru": "👤 <b>Клиенты</b>\n\nЗаписей пока нет.", "en": "👤 <b>Clients</b>\n\nNo bookings yet.", "fi": "👤 <b>Asiakkaat</b>\n\nEi varauksia vielä."},
    "client_visits":   {"ru": "📋 Визитов",    "en": "📋 Visits",    "fi": "📋 Käynnit"},
    "client_last":     {"ru": "📅 Последний",  "en": "📅 Last",      "fi": "📅 Viimeisin"},
    "client_paid":     {"ru": "✅ Оплачено",   "en": "✅ Paid",      "fi": "✅ Maksettu"},
    "client_of":       {"ru": "из",           "en": "of",           "fi": "/"},
    "client_noshows":  {"ru": "🚫 Неявок",    "en": "🚫 No-shows",  "fi": "🚫 Ei-saapunut"},
    "client_cancels":  {"ru": "❌ Отмен",     "en": "❌ Cancels",   "fi": "❌ Peruutukset"},
    "client_services": {"ru": "💅 Услуги",    "en": "💅 Services",  "fi": "💅 Palvelut"},
    "client_notes":    {"ru": "📝 Заметки",   "en": "📝 Notes",     "fi": "📝 Muistiinpanot"},
    "btn_back_clients":{"ru": "← К списку",  "en": "← Back",       "fi": "← Takaisin"},
    "btn_back_main":   {"ru": "← Назад",     "en": "← Back",       "fi": "← Takaisin"},

    # ── Help text ─────────────────────────────────────────────────────────────
    "help_text": {
        "ru": (
            "❓ <b>Помощь — что умеет Aria</b>\n\n"
            "📅 <b>Сегодня / Завтра</b> — расписание на день\n"
            "📋 <b>Ближайшие</b> — записи на 14 дней вперёд\n"
            "➕ <b>Новая запись</b> — услуга → дата → время → клиент\n\n"
            "👤 <b>Клиенты</b> — история визитов, расходы, заметки\n"
            "   🆕 новый · ⭐ постоянный · ⚠️ рискованный\n"
            "💰 <b>Финансы</b> — выручка, средний чек, % мастера\n"
            "📊 <b>Аналитика</b> — топ услуги, топ клиенты, рискованные\n"
            "⏰ <b>Напоминания</b> — за X ч до записи + сводка на завтра\n\n"
            "<b>Тап по записи:</b>\n"
            "✅ Пришёл · 🚫 Не пришёл · 💰 Оплата\n"
            "✏️ Перенести · 📝 Заметка · ❌ Отменить\n\n"
            "<b>Aria понимает обычные сообщения:</b>\n"
            "• «запиши Катю на стрижку 20 мая в 14:00»\n"
            "• «перенеси Катю на завтра»\n"
            "• «что свободно вечером?»\n"
            "• «кто давно не приходил?»\n\n"
            "📧 <b>Почта</b> — пересылает письма от букинг-сервисов прямо в Telegram\n\n"
            "<b>Команды:</b> /reset · /status"
        ),
        "en": (
            "❓ <b>Help — what Aria can do</b>\n\n"
            "📅 <b>Today / Tomorrow</b> — daily schedule\n"
            "📋 <b>Upcoming</b> — bookings for the next 14 days\n"
            "➕ <b>New booking</b> — service → date → time → client\n\n"
            "👤 <b>Clients</b> — visit history, spending, notes\n"
            "   🆕 new · ⭐ regular · ⚠️ at-risk\n"
            "💰 <b>Finances</b> — revenue, avg. ticket, master share\n"
            "📊 <b>Analytics</b> — top services, top clients, at-risk\n"
            "⏰ <b>Reminders</b> — X hours before + tomorrow's summary\n\n"
            "<b>Tap a booking:</b>\n"
            "✅ Arrived · 🚫 No-show · 💰 Payment\n"
            "✏️ Reschedule · 📝 Note · ❌ Cancel\n\n"
            "<b>Aria understands plain messages:</b>\n"
            "• «book Kate for a haircut May 20 at 14:00»\n"
            "• «reschedule Kate to tomorrow»\n"
            "• «what's free this evening?»\n"
            "• «who hasn't visited in a while?»\n\n"
            "📧 <b>Email</b> — forwards booking-service emails to Telegram\n\n"
            "<b>Commands:</b> /reset · /status"
        ),
        "fi": (
            "❓ <b>Ohje — mitä Aria osaa</b>\n\n"
            "📅 <b>Tänään / Huomenna</b> — päivän aikataulu\n"
            "📋 <b>Tulevat</b> — varaukset seuraavalle 14 päivälle\n"
            "➕ <b>Uusi varaus</b> — palvelu → päivä → aika → asiakas\n\n"
            "👤 <b>Asiakkaat</b> — käyntihistoria, kulutus, muistiinpanot\n"
            "   🆕 uusi · ⭐ kanta-asiakas · ⚠️ riskiasiakas\n"
            "💰 <b>Talous</b> — tulot, keskim. hinta, mestarin osuus\n"
            "📊 <b>Analytiikka</b> — top palvelut, top asiakkaat, riskiasiakkaat\n"
            "⏰ <b>Muistutukset</b> — X tuntia ennen + huomisen yhteenveto\n\n"
            "<b>Napauta varausta:</b>\n"
            "✅ Saapui · 🚫 Ei saapunut · 💰 Maksu\n"
            "✏️ Siirrä · 📝 Muistiinpano · ❌ Peruuta\n\n"
            "<b>Aria ymmärtää tavalliset viestit:</b>\n"
            "• «varaa Kaisa hiustenleikkaukseen 20.5. klo 14:00»\n"
            "• «siirrä Kaisa huomiselle»\n"
            "• «mitä on vapaana illalla?»\n"
            "• «kenellä ei ole ollut käyntiä pitkään?»\n\n"
            "📧 <b>Sähköposti</b> — välittää varauspalvelujen sähköpostit Telegramiin\n\n"
            "<b>Komennot:</b> /reset · /status"
        ),
    },

    # ── Language chooser ──────────────────────────────────────────────────────
    "lang_title":  {"ru": "🌐 <b>Язык интерфейса</b>", "en": "🌐 <b>Interface language</b>", "fi": "🌐 <b>Käyttöliittymän kieli</b>"},
    "lang_choose": {"ru": "Выбери язык:",               "en": "Choose language:",              "fi": "Valitse kieli:"},
    "lang_saved":  {"ru": "✅ Язык: Русский 🇷🇺",       "en": "✅ Language: English 🇬🇧",       "fi": "✅ Kieli: Suomi 🇫🇮"},

    # ── Scheduler / owner notifications ──────────────────────────────────────
    "sched_no_tomorrow": {
        "ru": "📋 Завтра записей нет — свободный день! 🎉",
        "en": "📋 No bookings tomorrow — free day! 🎉",
        "fi": "📋 Ei varauksia huomenna — vapaa päivä! 🎉",
    },
    "sched_noshow": {
        "ru": "❓ {client} пришла в {time}? ({service})\n\nОтветь «да» или «нет» — я обновлю запись.",
        "en": "❓ Did {client} arrive at {time}? ({service})\n\nReply «yes» or «no» — I'll update the booking.",
        "fi": "❓ Saapuiko {client} klo {time}? ({service})\n\nVastaa «kyllä» tai «ei» — päivitän varauksen.",
    },
    "sched_waitlist": {
        "ru": "🟢 Открылось свободное окно! Проверь лист ожидания.",
        "en": "🟢 A slot just opened! Check the waitlist.",
        "fi": "🟢 Vapaa aika avautui! Tarkista jonotuslistasi.",
    },
    "sched_summary_header": {
        "ru": "📋 <b>Завтра ({day}) — {n} зап.</b>",
        "en": "📋 <b>Tomorrow ({day}) — {n} booking(s).</b>",
        "fi": "📋 <b>Huomenna ({day}) — {n} varaus(ta).</b>",
    },
    "sched_reactivation": {
        "ru": "💤 Клиенты без визита 45+ дней{suffix}:\n\n{names}",
        "en": "💤 Clients without a visit for 45+ days{suffix}:\n\n{names}",
        "fi": "💤 Asiakkaat ilman käyntiä 45+ päivää{suffix}:\n\n{names}",
    },
    "sched_reactivation_more": {
        "ru": " (первые 10 из {total})",
        "en": " (first 10 of {total})",
        "fi": " (ensimmäiset 10 / {total})",
    },
    "sched_in": {
        "ru": "в",
        "en": "at",
        "fi": "klo",
    },

    # ── Service catalogue ─────────────────────────────────────────────────────
    "cat_mgmt_title": {"ru": "👩‍💼 <b>Управление услугами</b>\n\nНажмите на категорию или добавьте новую.", "en": "👩‍💼 <b>Service management</b>\n\nTap a category or add a new one.", "fi": "👩‍💼 <b>Palvelujen hallinta</b>\n\nNapauta kategoriaa tai lisää uusi."},
    "cat_add_btn":    {"ru": "➕ Добавить категорию",  "en": "➕ Add category",   "fi": "➕ Lisää kategoria"},
    "cat_added":      {"ru": "✅ Категория «{name}» добавлена.", "en": "✅ Category «{name}» added.", "fi": "✅ Kategoria «{name}» lisätty."},
    "cat_deleted":    {"ru": "🗑 Категория удалена.",   "en": "🗑 Category deleted.",   "fi": "🗑 Kategoria poistettu."},
    "cat_not_empty":  {"ru": "Название не может быть пустым. Попробуйте снова:", "en": "Name can't be empty. Try again:", "fi": "Nimi ei voi olla tyhjä. Yritä uudelleen:"},
    "cat_prompt":     {"ru": "Введите название новой категории:", "en": "Enter the new category name:", "fi": "Syötä uuden kategorian nimi:"},
    "item_add_btn":   {"ru": "➕ Добавить услугу",     "en": "➕ Add service",     "fi": "➕ Lisää palvelu"},
    "item_edit_btn":  {"ru": "✏️ Изменить",            "en": "✏️ Edit",            "fi": "✏️ Muokkaa"},
    "item_del_btn":   {"ru": "🗑 Удалить",             "en": "🗑 Delete",          "fi": "🗑 Poista"},
    "item_deleted":   {"ru": "Услуга удалена",         "en": "Service deleted",    "fi": "Palvelu poistettu"},
    "item_prompt":    {"ru": "Введите название услуги для «{cat}»:", "en": "Enter service name for «{cat}»:", "fi": "Syötä palvelun nimi kategoriaan «{cat}»:"},
    "item_added":     {"ru": "✅ Услуга «{name}» добавлена", "en": "✅ Service «{name}» added", "fi": "✅ Palvelu «{name}» lisätty"},
    "item_price_lbl": {"ru": "Цена",     "en": "Price",    "fi": "Hinta"},
    "item_dur_lbl":   {"ru": "Длит.",    "en": "Dur.",     "fi": "Kesto"},
    "item_edit_what": {"ru": "Что редактировать?",  "en": "What to edit?", "fi": "Mitä muokata?"},
    "price_prompt":   {"ru": "💰 Цена услуги «{name}» (например: <code>50</code>)\nИли /skip чтобы не указывать.", "en": "💰 Price for «{name}» (e.g. <code>50</code>)\nOr /skip to leave empty.", "fi": "💰 Palvelun «{name}» hinta (esim. <code>50</code>)\nTai /skip ohittaaksesi."},
    "price_edit_prompt": {"ru": "💰 Введи новую цену (например: <code>50</code>)\nИли /skip чтобы убрать цену.", "en": "💰 Enter new price (e.g. <code>50</code>)\nOr /skip to remove.", "fi": "💰 Syötä uusi hinta (esim. <code>50</code>)\nTai /skip poistaaksesi."},
    "price_bad":      {"ru": "Введите число, например <code>50</code>, или /skip:", "en": "Enter a number, e.g. <code>50</code>, or /skip:", "fi": "Syötä luku, esim. <code>50</code>, tai /skip:"},
    "price_deleted":  {"ru": "✅ Цена удалена.",       "en": "✅ Price removed.",  "fi": "✅ Hinta poistettu."},
    "price_updated":  {"ru": "✅ Цена обновлена:",     "en": "✅ Price updated:",  "fi": "✅ Hinta päivitetty:"},
    "dur_prompt":     {"ru": "⏱ Длительность в минутах (например: <code>60</code>)\nИли /skip чтобы не указывать.", "en": "⏱ Duration in minutes (e.g. <code>60</code>)\nOr /skip to leave empty.", "fi": "⏱ Kesto minuuteissa (esim. <code>60</code>)\nTai /skip ohittaaksesi."},
    "dur_bad":        {"ru": "Введите целое число минут, например <code>60</code>, или /skip:", "en": "Enter whole minutes, e.g. <code>60</code>, or /skip:", "fi": "Syötä kokonaisluku minuutteina, esim. <code>60</code>, tai /skip:"},
    "dur_deleted":    {"ru": "✅ Длительность удалена.", "en": "✅ Duration removed.", "fi": "✅ Kesto poistettu."},
    "dur_updated":    {"ru": "✅ Длительность обновлена:", "en": "✅ Duration updated:", "fi": "✅ Kesto päivitetty:"},
    "min_lbl":        {"ru": "мин",     "en": "min",     "fi": "min"},
    "cat_items_hdr":  {"ru": "📂 <b>{name}</b> — {n} услуг(а)\n\nНажмите 🗑 рядом с услугой, чтобы удалить.", "en": "📂 <b>{name}</b> — {n} service(s)\n\nTap 🗑 next to a service to delete it.", "fi": "📂 <b>{name}</b> — {n} palvelu(a)\n\nNapauta 🗑 palvelun vieressä poistaaksesi."},
}


# ── Public API ────────────────────────────────────────────────────────────────

def t(key: str, lang: str = "ru") -> str:
    """Return translated string for key + lang, falling back to Russian."""
    entry = T.get(key)
    if entry is None:
        return key
    if isinstance(entry, dict) and set(entry.keys()) <= {"ru", "en", "fi"}:
        return entry.get(lang) or entry.get("ru", key)
    return str(entry)


def all_variants(key: str) -> frozenset[str]:
    """Return all language variants of a keyboard-button key."""
    entry = T.get(key, {})
    return frozenset(entry.values())


def fmt_time_label(mins_left: int, hours_before: int, lang: str) -> str:
    """Format reminder time label: 'через 2 ч' / 'in 2 h' / '2 t päästä'."""
    pre  = t("in_prefix", lang)
    h_u  = t("in_h",   lang)
    m_u  = t("in_min", lang)
    suf  = t("in_suffix", lang)
    if mins_left > 90:
        core = f"{hours_before} {h_u}"
    elif mins_left > 0:
        core = f"{mins_left} {m_u}"
    else:
        return {"ru": "скоро", "en": "soon", "fi": "pian"}.get(lang, "soon")
    if lang == "fi":
        return f"{core}{suf}"
    return f"{pre} {core}{suf}".strip()
