"""Structured booking FSM — multilingual, timezone-aware."""

from __future__ import annotations

import logging
import re
import zoneinfo
from datetime import date, datetime, time, timedelta, timezone
from typing import Union

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import aria.db.repo as repo
from aria.config import TenantConfig
from aria.services import gcal

log = logging.getLogger(__name__)
router = Router()


class BookingSG(StatesGroup):
    client_name = State()
    pick_date   = State()
    pick_time   = State()
    confirm     = State()


# ── Language helpers ──────────────────────────────────────────────────────────

_SUPPORTED = {"ru","en","uk","fi","de","fr","es","it","pl","sv","nl","no","da","tr","he","ar"}

def _normalize_lang(code: str) -> str:
    if not code:
        return "en"
    base = code.split("-")[0].lower()
    return base if base in _SUPPORTED else "en"

# All user-facing strings keyed by message key then language code
_T: dict[str, dict[str, str]] = {
    "new_booking": {
        "ru":"📋 <b>Новая запись</b>","en":"📋 <b>New booking</b>",
        "uk":"📋 <b>Новий запис</b>","fi":"📋 <b>Uusi varaus</b>",
        "de":"📋 <b>Neue Buchung</b>","fr":"📋 <b>Nouveau rendez-vous</b>",
        "es":"📋 <b>Nueva reserva</b>","it":"📋 <b>Nuova prenotazione</b>",
        "pl":"📋 <b>Nowa rezerwacja</b>","sv":"📋 <b>Ny bokning</b>",
        "nl":"📋 <b>Nieuwe boeking</b>","no":"📋 <b>Ny bestilling</b>",
        "da":"📋 <b>Ny booking</b>","tr":"📋 <b>Yeni rezervasyon</b>",
    },
    "service_label": {
        "ru":"💅 Услуга:","en":"💅 Service:","uk":"💅 Послуга:",
        "fi":"💅 Palvelu:","de":"💅 Dienst:","fr":"💅 Service :",
        "es":"💅 Servicio:","it":"💅 Servizio:","pl":"💅 Usługa:",
        "sv":"💅 Tjänst:","nl":"💅 Dienst:","no":"💅 Tjeneste:",
        "da":"💅 Ydelse:","tr":"💅 Hizmet:",
    },
    "enter_name": {
        "ru":"👤 Введите имя клиента:","en":"👤 Enter client name:",
        "uk":"👤 Введіть ім'я клієнта:","fi":"👤 Syötä asiakkaan nimi:",
        "de":"👤 Kundenname eingeben:","fr":"👤 Nom du client :",
        "es":"👤 Nombre del cliente:","it":"👤 Nome del cliente:",
        "pl":"👤 Imię klienta:","sv":"👤 Ange kundens namn:",
        "nl":"👤 Naam klant:","no":"👤 Kundens navn:","da":"👤 Kundenavn:",
        "tr":"👤 Müşteri adı:",
    },
    "select_date": {
        "ru":"📅 Выберите дату:","en":"📅 Select date:",
        "uk":"📅 Оберіть дату:","fi":"📅 Valitse päivä:",
        "de":"📅 Datum wählen:","fr":"📅 Choisissez la date :",
        "es":"📅 Seleccione fecha:","it":"📅 Seleziona data:",
        "pl":"📅 Wybierz datę:","sv":"📅 Välj datum:",
        "nl":"📅 Selecteer datum:","no":"📅 Velg dato:","da":"📅 Vælg dato:",
        "tr":"📅 Tarih seçin:",
    },
    "select_time": {
        "ru":"⏰ {date} — выберите время:","en":"⏰ {date} — select time:",
        "uk":"⏰ {date} — оберіть час:","fi":"⏰ {date} — valitse aika:",
        "de":"⏰ {date} — Uhrzeit wählen:","fr":"⏰ {date} — choisissez l'heure :",
        "es":"⏰ {date} — seleccione hora:","it":"⏰ {date} — seleziona orario:",
        "pl":"⏰ {date} — wybierz godzinę:","sv":"⏰ {date} — välj tid:",
        "nl":"⏰ {date} — selecteer tijd:","no":"⏰ {date} — velg tid:",
        "da":"⏰ {date} — vælg tid:","tr":"⏰ {date} — saat seçin:",
    },
    "review": {
        "ru":"📋 <b>Проверьте запись:</b>","en":"📋 <b>Review booking:</b>",
        "uk":"📋 <b>Перевірте запис:</b>","fi":"📋 <b>Tarkista varaus:</b>",
        "de":"📋 <b>Buchung prüfen:</b>","fr":"📋 <b>Vérifiez le rendez-vous :</b>",
        "es":"📋 <b>Revisar reserva:</b>","it":"📋 <b>Controlla prenotazione:</b>",
        "pl":"📋 <b>Sprawdź rezerwację:</b>","sv":"📋 <b>Granska bokning:</b>",
        "nl":"📋 <b>Boeking controleren:</b>","no":"📋 <b>Sjekk bestilling:</b>",
        "da":"📋 <b>Gennemse booking:</b>","tr":"📋 <b>Rezervasyonu kontrol edin:</b>",
    },
    "client_label": {
        "ru":"👤 Клиент:","en":"👤 Client:","uk":"👤 Клієнт:","fi":"👤 Asiakas:",
        "de":"👤 Kunde:","fr":"👤 Client :","es":"👤 Cliente:","it":"👤 Cliente:",
        "pl":"👤 Klient:","sv":"👤 Kund:","nl":"👤 Klant:","no":"👤 Kunde:",
        "da":"👤 Kunde:","tr":"👤 Müşteri:",
    },
    "confirmed": {
        "ru":"✅ <b>Запись создана!</b>","en":"✅ <b>Booking confirmed!</b>",
        "uk":"✅ <b>Запис підтверджено!</b>","fi":"✅ <b>Varaus vahvistettu!</b>",
        "de":"✅ <b>Buchung bestätigt!</b>","fr":"✅ <b>Rendez-vous confirmé !</b>",
        "es":"✅ <b>¡Reserva confirmada!</b>","it":"✅ <b>Prenotazione confermata!</b>",
        "pl":"✅ <b>Rezerwacja potwierdzona!</b>","sv":"✅ <b>Bokning bekräftad!</b>",
        "nl":"✅ <b>Boeking bevestigd!</b>","no":"✅ <b>Bestilling bekreftet!</b>",
        "da":"✅ <b>Booking bekræftet!</b>","tr":"✅ <b>Rezervasyon onaylandı!</b>",
    },
    "gcal_added": {
        "ru":"\n📆 Добавлено в Google Calendar","en":"\n📆 Added to Google Calendar",
        "uk":"\n📆 Додано до Google Calendar","fi":"\n📆 Lisätty Google Kalenteriin",
        "de":"\n📆 Zu Google Kalender hinzugefügt","fr":"\n📆 Ajouté à Google Agenda",
        "es":"\n📆 Añadido a Google Calendar","it":"\n📆 Aggiunto a Google Calendar",
        "pl":"\n📆 Dodano do Kalendarza Google","sv":"\n📆 Tillagd i Google Kalender",
        "nl":"\n📆 Toegevoegd aan Google Agenda",
    },
    "btn_confirm": {
        "ru":"✅ Создать запись","en":"✅ Confirm booking","uk":"✅ Підтвердити запис",
        "fi":"✅ Vahvista varaus","de":"✅ Buchung bestätigen","fr":"✅ Confirmer",
        "es":"✅ Confirmar","it":"✅ Conferma","pl":"✅ Potwierdź",
        "sv":"✅ Bekräfta","nl":"✅ Bevestigen","no":"✅ Bekreft","da":"✅ Bekræft",
        "tr":"✅ Onayla",
    },
    "btn_cancel": {
        "ru":"❌ Отмена","en":"❌ Cancel","uk":"❌ Скасувати","fi":"❌ Peruuta",
        "de":"❌ Abbrechen","fr":"❌ Annuler","es":"❌ Cancelar","it":"❌ Annulla",
        "pl":"❌ Anuluj","sv":"❌ Avbryt","nl":"❌ Annuleren","no":"❌ Avbryt",
        "da":"❌ Annuller","tr":"❌ İptal",
    },
    "btn_back_date": {
        "ru":"← Назад к дате","en":"← Back to date","uk":"← Назад до дати",
        "fi":"← Takaisin","de":"← Zurück","fr":"← Retour","es":"← Volver",
        "it":"← Indietro","pl":"← Wróć","sv":"← Tillbaka","nl":"← Terug",
        "no":"← Tilbake","da":"← Tilbage","tr":"← Geri",
    },
    "btn_other_day": {
        "ru":"📝 Другой день...","en":"📝 Other day...","uk":"📝 Інший день...",
        "fi":"📝 Muu päivä...","de":"📝 Anderer Tag...","fr":"📝 Autre jour...",
        "es":"📝 Otro día...","it":"📝 Altro giorno...","pl":"📝 Inny dzień...",
        "sv":"📝 Annan dag...","nl":"📝 Andere dag...","no":"📝 Annen dag...",
        "da":"📝 Anden dag...","tr":"📝 Başka gün...",
    },
    "other_day_prompt": {
        "ru":"📅 Введите дату:\n<i>Например: завтра · 23 мая · 23.05</i>",
        "en":"📅 Enter date:\n<i>E.g.: tomorrow · 23 May · 23.05</i>",
        "uk":"📅 Введіть дату:\n<i>Наприклад: завтра · 23 травня · 23.05</i>",
        "fi":"📅 Syötä päivämäärä:\n<i>Esim.: huomenna · 23 toukokuuta · 23.05</i>",
        "de":"📅 Datum eingeben:\n<i>Z.B.: morgen · 23. Mai · 23.05</i>",
        "fr":"📅 Entrez la date :\n<i>Ex. : demain · 23 mai · 23.05</i>",
        "es":"📅 Ingrese fecha:\n<i>Ej.: mañana · 23 mayo · 23.05</i>",
        "it":"📅 Inserisci data:\n<i>Es.: domani · 23 maggio · 23.05</i>",
        "pl":"📅 Wpisz datę:\n<i>Np.: jutro · 23 maja · 23.05</i>",
        "sv":"📅 Ange datum:\n<i>T.ex.: imorgon · 23 maj · 23.05</i>",
        "nl":"📅 Voer datum in:\n<i>Bijv.: morgen · 23 mei · 23.05</i>",
    },
    "date_error": {
        "ru":"Не могу распознать дату. Попробуйте:\n• <i>завтра</i>\n• <i>23 мая</i>\n• <i>23.05</i>",
        "en":"Can't parse that date. Try:\n• <i>tomorrow</i>\n• <i>23 May</i>\n• <i>23.05</i>",
        "uk":"Не можу розпізнати дату:\n• <i>завтра</i>\n• <i>23 травня</i>\n• <i>23.05</i>",
        "fi":"En tunnista päivämäärää:\n• <i>huomenna</i>\n• <i>23 toukokuuta</i>\n• <i>23.05</i>",
        "de":"Datum nicht erkannt:\n• <i>morgen</i>\n• <i>23. Mai</i>\n• <i>23.05</i>",
        "fr":"Date non reconnue :\n• <i>demain</i>\n• <i>23 mai</i>\n• <i>23.05</i>",
        "es":"No reconozco la fecha:\n• <i>mañana</i>\n• <i>23 mayo</i>\n• <i>23.05</i>",
        "it":"Data non riconosciuta:\n• <i>domani</i>\n• <i>23 maggio</i>\n• <i>23.05</i>",
        "pl":"Nie rozumiem daty:\n• <i>jutro</i>\n• <i>23 maja</i>\n• <i>23.05</i>",
        "sv":"Kunde inte läsa datumet:\n• <i>imorgon</i>\n• <i>23 maj</i>\n• <i>23.05</i>",
    },
    "cancelled": {
        "ru":"Запись отменена.","en":"Booking cancelled.","uk":"Запис скасовано.",
        "fi":"Varaus peruttu.","de":"Buchung storniert.","fr":"Rendez-vous annulé.",
        "es":"Reserva cancelada.","it":"Prenotazione annullata.","pl":"Rezerwacja anulowana.",
        "sv":"Bokning avbokad.","nl":"Boeking geannuleerd.","no":"Bestilling avlyst.",
        "da":"Booking annulleret.","tr":"Rezervasyon iptal edildi.",
    },
    "stale_session": {
        "ru":"Сессия устарела — начните новую запись.",
        "en":"Session expired — please start a new booking.",
        "fi":"Istunto vanhentunut — aloita uusi varaus.",
        "de":"Sitzung abgelaufen — neue Buchung starten.",
        "fr":"Session expirée — recommencez.",
        "uk":"Сесія застаріла — почніть новий запис.",
    },
}


def _t(key: str, lang: str) -> str:
    d = _T.get(key, {})
    return d.get(lang) or d.get("en") or key


# ── Date/time helpers ─────────────────────────────────────────────────────────

_MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_MONTHS_SHORT = ("янв", "фев", "мар", "апр", "май", "июн",
                 "июл", "авг", "сен", "окт", "ноя", "дек")
_DAYS_SHORT   = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _fmt_date(d: date) -> str:
    return f"{d.day} {_MONTHS_SHORT[d.month - 1]} ({_DAYS_SHORT[d.weekday()]})"


def _get_tz(tz_name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return zoneinfo.ZoneInfo("Europe/Moscow")


def _today_in_tz(tz_name: str) -> date:
    return datetime.now(_get_tz(tz_name)).date()


def _parse_date(text: str) -> date | None:
    text = text.strip().lower()
    today = date.today()

    if "послезавтра" in text or "day after tomorrow" in text:
        return today + timedelta(days=2)
    if "завтра" in text or "tomorrow" in text or "huomenna" in text or "morgen" in text:
        return today + timedelta(days=1)
    if "сегодня" in text or "today" in text or "heute" in text or "aujourd" in text:
        return today

    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", text)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        yr = int(m.group(3)) if m.group(3) else today.year
        if yr < 100:
            yr += 2000
        try:
            d = date(yr, mon, day)
            return d if d >= today else date(yr + 1, mon, day)
        except ValueError:
            return None

    for name, mon in _MONTHS_RU.items():
        m2 = re.search(rf"\b(\d{{1,2}})\s+{name}\b", text)
        if m2:
            day = int(m2.group(1))
            yr = today.year
            try:
                d = date(yr, mon, day)
                return d if d >= today else date(yr + 1, mon, day)
            except ValueError:
                return None
    return None


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _date_kb(tz_name: str, lang: str) -> InlineKeyboardMarkup:
    today = _today_in_tz(tz_name)
    rows = []
    for i in range(5):
        d = today + timedelta(days=i)
        rows.append([InlineKeyboardButton(
            text=f"{_fmt_date(d)}",
            callback_data=f"book:d:{d.isoformat()}",
        )])
    rows.append([InlineKeyboardButton(text=_t("btn_other_day", lang), callback_data="book:d:other")])
    rows.append([InlineKeyboardButton(text=_t("btn_cancel", lang),    callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _time_kb(tenant: TenantConfig, lang: str) -> InlineKeyboardMarkup:
    step = max(tenant.salon_slot_minutes, 30)
    slots: list[str] = []
    minutes = tenant.salon_open_hour * 60
    end = tenant.salon_close_hour * 60
    while minutes < end:
        h, m = divmod(minutes, 60)
        slots.append(f"{h:02d}:{m:02d}")
        minutes += step

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slot in slots:
        row.append(InlineKeyboardButton(text=slot, callback_data=f"book:t:{slot}"))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text=_t("btn_back_date", lang), callback_data="book:back:date")])
    rows.append([InlineKeyboardButton(text=_t("btn_cancel", lang),    callback_data="book:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=_t("btn_confirm", lang), callback_data="book:confirm"),
        InlineKeyboardButton(text=_t("btn_cancel",  lang), callback_data="book:cancel"),
    ]])


# ── Entry point ───────────────────────────────────────────────────────────────

async def start_booking(
    event: Union[Message, CallbackQuery],
    state: FSMContext,
    tenant: TenantConfig,
    service: str,
) -> None:
    """Called after a service is selected. Detects user language and tz."""
    user = event.from_user
    lang = _normalize_lang(user.language_code or "")
    tz_name = await repo.get_tenant_timezone(tenant.tenant_id)

    # Persist language so it survives across sessions
    await repo.set_client_lang(user.id, lang)

    await state.set_state(BookingSG.client_name)
    await state.update_data(
        service=service,
        tenant_id=tenant.tenant_id,
        tz_name=tz_name,
        lang=lang,
    )
    text = (
        f"{_t('new_booking', lang)}\n"
        f"{_t('service_label', lang)} <b>{service}</b>\n\n"
        f"{_t('enter_name', lang)}"
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML")
    else:
        await event.answer(text, parse_mode="HTML")


# ── Client name ───────────────────────────────────────────────────────────────

@router.message(BookingSG.client_name)
async def got_client_name(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    name = (message.text or "").strip()
    if not name:
        data = await state.get_data()
        await message.answer(_t("enter_name", data.get("lang", "en")))
        return
    data = await state.get_data()
    lang    = data.get("lang", "en")
    tz_name = data.get("tz_name", tenant.salon_timezone)
    await state.update_data(client_name=name)
    await state.set_state(BookingSG.pick_date)
    await message.answer(_t("select_date", lang), reply_markup=_date_kb(tz_name, lang))


# ── Date selection ────────────────────────────────────────────────────────────

@router.callback_query(BookingSG.pick_date, F.data.startswith("book:d:"))
async def got_date_button(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    data = await state.get_data()
    lang = data.get("lang", "en")
    raw  = callback.data[len("book:d:"):]

    if raw == "other":
        await callback.message.edit_text(
            _t("other_day_prompt", lang), parse_mode="HTML"
        )
        await callback.answer()
        return

    try:
        d = date.fromisoformat(raw)
    except ValueError:
        await callback.answer("?")
        return

    await state.update_data(chosen_date=raw)
    await state.set_state(BookingSG.pick_time)
    await callback.message.edit_text(
        _t("select_time", lang).format(date=_fmt_date(d)),
        parse_mode="HTML",
        reply_markup=_time_kb(tenant, lang),
    )
    await callback.answer()


@router.message(BookingSG.pick_date)
async def got_date_text(message: Message, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    lang = data.get("lang", "en")
    d = _parse_date(message.text or "")
    if not d:
        await message.answer(_t("date_error", lang), parse_mode="HTML")
        return
    await state.update_data(chosen_date=d.isoformat())
    await state.set_state(BookingSG.pick_time)
    await message.answer(
        _t("select_time", lang).format(date=_fmt_date(d)),
        parse_mode="HTML",
        reply_markup=_time_kb(tenant, lang),
    )


# ── Time selection ────────────────────────────────────────────────────────────

@router.callback_query(BookingSG.pick_time, F.data == "book:back:date")
async def back_to_date(callback: CallbackQuery, state: FSMContext, tenant: TenantConfig) -> None:
    data = await state.get_data()
    lang    = data.get("lang", "en")
    tz_name = data.get("tz_name", tenant.salon_timezone)
    await state.set_state(BookingSG.pick_date)
    await callback.message.edit_text(
        _t("select_date", lang), reply_markup=_date_kb(tz_name, lang)
    )
    await callback.answer()


@router.callback_query(BookingSG.pick_time, F.data.startswith("book:t:"))
async def got_time(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    data = await state.get_data()
    lang     = data.get("lang", "en")
    time_str = callback.data[len("book:t:"):]
    d        = date.fromisoformat(data["chosen_date"])
    dt_display = f"{_fmt_date(d)} {time_str}"

    await state.update_data(chosen_time=time_str, dt_display=dt_display)
    await state.set_state(BookingSG.confirm)

    await callback.message.edit_text(
        f"{_t('review', lang)}\n\n"
        f"{_t('client_label', lang)} <b>{data['client_name']}</b>\n"
        f"{_t('service_label', lang)} <b>{data['service']}</b>\n"
        f"📅 {dt_display}",
        parse_mode="HTML",
        reply_markup=_confirm_kb(lang),
    )
    await callback.answer()


# ── Confirm / Cancel ──────────────────────────────────────────────────────────

@router.callback_query(BookingSG.confirm, F.data == "book:confirm")
async def confirm_booking(
    callback: CallbackQuery, state: FSMContext, tenant: TenantConfig
) -> None:
    data = await state.get_data()
    lang = data.get("lang", "en")
    await state.clear()

    try:
        d = date.fromisoformat(data["chosen_date"])
        h, m = map(int, data["chosen_time"].split(":"))
        tz_name = data.get("tz_name", tenant.salon_timezone)
        tz = _get_tz(tz_name)
        scheduled_at = datetime.combine(d, time(h, m)).replace(tzinfo=tz)
        client_name  = data["client_name"]
        service      = data["service"]

        booking_id = await repo.create_booking(
            user_id=callback.from_user.id,
            client_name=client_name,
            service=service,
            scheduled_at=scheduled_at,
        )
    except Exception:
        log.exception("Booking creation failed (tenant #%d)", tenant.tenant_id)
        await callback.answer(
            _t("stale_session", lang) if "chosen_date" not in data
            else "❌ Error creating booking. Please try again.",
            show_alert=True,
        )
        return

    gcal_event_url = ""
    try:
        if await gcal.is_connected(tenant.tenant_id):
            result = await gcal.create_event(
                tenant_id=tenant.tenant_id,
                client_name=client_name,
                service=service,
                scheduled_at=scheduled_at,
                duration_minutes=tenant.salon_slot_minutes,
                tz=tz_name,
            )
            if result:
                event_id, gcal_event_url = result
                await repo.update_booking_gcal_event(booking_id, event_id)
    except Exception:
        log.exception("GCal event creation failed (tenant #%d)", tenant.tenant_id)

    if gcal_event_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📅 Google Calendar", url=gcal_event_url),
        ]])
        gcal_note = _t("gcal_added", lang)
    else:
        fallback_url = gcal.add_to_calendar_url(
            title=f"{service} — {client_name}",
            start=scheduled_at,
            duration_minutes=tenant.salon_slot_minutes,
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📅 Google Calendar", url=fallback_url),
        ]])
        gcal_note = ""

    await callback.message.edit_text(
        f"{_t('confirmed', lang)}\n\n"
        f"{_t('client_label', lang)} {client_name}\n"
        f"{_t('service_label', lang)} {service}\n"
        f"📅 {data['dt_display']}"
        f"{gcal_note}",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "book:confirm")
async def confirm_booking_stale(callback: CallbackQuery) -> None:
    await callback.answer("Session expired — start a new booking.", show_alert=True)


@router.callback_query(F.data == "book:cancel")
async def cancel_booking(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("lang", "en")
    await state.clear()
    await callback.message.edit_text(_t("cancelled", lang))
    await callback.answer()


# ── Bookings list + deletion ──────────────────────────────────────────────────

async def show_bookings_list(
    target: Union[Message, CallbackQuery],
    user_id: int,
    tenant: TenantConfig,
) -> None:
    tz_name = await repo.get_tenant_timezone(tenant.tenant_id)
    tz = _get_tz(tz_name)
    bookings = await repo.get_upcoming_bookings(user_id, limit=10)
    new_btn = InlineKeyboardButton(text="➕ Новая запись", callback_data="new:booking")

    if not bookings:
        await _send(target, "📋 Нет предстоящих записей.", InlineKeyboardMarkup(
            inline_keyboard=[[new_btn]]
        ))
        return

    lines, rows = [], []
    for b in bookings:
        dt: datetime = b["scheduled_at"]
        dt = dt.astimezone(tz)
        d = dt.date()
        label = f"❌ {dt.strftime('%d.%m')} {dt.strftime('%H:%M')} — {b['client_name']}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"book:del:{b['id']}")])
        lines.append(
            f"📅 <b>{_fmt_date(d)}</b> {dt.strftime('%H:%M')}\n"
            f"👤 {b['client_name']} · 💅 {b['service']}"
        )
    rows.append([InlineKeyboardButton(text="🗑 Удалить все на дату", callback_data="book:del_date")])
    rows.append([new_btn])
    text = "📋 <b>Предстоящие записи:</b>\n\n" + "\n\n".join(lines)
    await _send(target, text, InlineKeyboardMarkup(inline_keyboard=rows))


async def _send(
    target: Union[Message, CallbackQuery],
    text: str,
    kb: InlineKeyboardMarkup,
) -> None:
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "book:list")
async def back_to_list(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    await show_bookings_list(callback, callback.from_user.id, tenant)


@router.callback_query(F.data.startswith("book:del:"))
async def ask_cancel_booking(callback: CallbackQuery) -> None:
    await callback.answer()
    booking_id = int(callback.data.split(":")[-1])
    booking = await repo.get_booking(booking_id)
    if not booking:
        await callback.answer("Not found.", show_alert=True)
        return
    dt: datetime = booking["scheduled_at"]
    if dt.tzinfo:
        dt = dt.astimezone()
    await callback.message.edit_text(
        f"❓ Cancel booking?\n\n"
        f"📅 <b>{_fmt_date(dt.date())}</b> {dt.strftime('%H:%M')}\n"
        f"👤 {booking['client_name']}\n"
        f"💅 {booking['service']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Yes, cancel", callback_data=f"book:del_yes:{booking_id}"),
            InlineKeyboardButton(text="← Back",        callback_data="book:list"),
        ]]),
    )


@router.callback_query(F.data.startswith("book:del_yes:"))
async def do_cancel_booking(callback: CallbackQuery, tenant: TenantConfig) -> None:
    booking_id = int(callback.data.split(":")[-1])
    booking = await repo.get_booking(booking_id)
    if not booking:
        await callback.answer("Already deleted.", show_alert=True)
        return
    await repo.update_booking_status(booking_id, "cancelled")
    if booking["calendar_event_id"]:
        try:
            await gcal.delete_event(tenant.tenant_id, booking["calendar_event_id"])
        except Exception:
            log.exception("GCal event deletion failed for booking #%d", booking_id)
    await callback.answer("Cancelled.", show_alert=True)
    await show_bookings_list(callback, callback.from_user.id, tenant)


# ── Delete all on date ────────────────────────────────────────────────────────

def _del_date_kb(tz_name: str) -> InlineKeyboardMarkup:
    today = _today_in_tz(tz_name)
    rows = []
    for i in range(7):
        d = today + timedelta(days=i)
        rows.append([InlineKeyboardButton(
            text=_fmt_date(d),
            callback_data=f"book:del_date:{d.isoformat()}",
        )])
    rows.append([InlineKeyboardButton(text="← Back", callback_data="book:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "book:del_date")
async def pick_date_for_bulk_delete(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    tz_name = await repo.get_tenant_timezone(tenant.tenant_id)
    await callback.message.edit_text(
        "🗑 <b>Delete all bookings on date</b>\n\nSelect date:",
        parse_mode="HTML",
        reply_markup=_del_date_kb(tz_name),
    )


@router.callback_query(F.data.startswith("book:del_date:"))
async def confirm_bulk_delete(callback: CallbackQuery, tenant: TenantConfig) -> None:
    await callback.answer()
    raw = callback.data[len("book:del_date:"):]
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return
    tz_name  = await repo.get_tenant_timezone(tenant.tenant_id)
    bookings = await repo.get_bookings_on_date(callback.from_user.id, d, tz_name)
    if not bookings:
        await callback.message.edit_text(
            f"No bookings on <b>{_fmt_date(d)}</b>.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="← Back", callback_data="book:list"),
            ]]),
        )
        return
    names = ", ".join(b["client_name"] for b in bookings)
    await callback.message.edit_text(
        f"🗑 Delete <b>all {len(bookings)}</b> bookings on <b>{_fmt_date(d)}</b>?\n\n👤 {names}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"✅ Delete all ({len(bookings)})",
                                 callback_data=f"book:del_date_yes:{raw}"),
            InlineKeyboardButton(text="← Back", callback_data="book:list"),
        ]]),
    )


@router.callback_query(F.data.startswith("book:del_date_yes:"))
async def do_bulk_delete(callback: CallbackQuery, tenant: TenantConfig) -> None:
    raw = callback.data[len("book:del_date_yes:"):]
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return
    tz_name   = await repo.get_tenant_timezone(tenant.tenant_id)
    cancelled = await repo.cancel_bookings_on_date(callback.from_user.id, d, tz_name)
    for b in cancelled:
        if b["calendar_event_id"]:
            try:
                await gcal.delete_event(tenant.tenant_id, b["calendar_event_id"])
            except Exception:
                log.exception("GCal bulk delete failed for booking #%d", b["id"])
    await callback.answer(f"Deleted {len(cancelled)}.", show_alert=True)
    await show_bookings_list(callback, callback.from_user.id, tenant)
