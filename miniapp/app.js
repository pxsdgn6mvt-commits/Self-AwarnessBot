/**
 * Aria Mini App — shared JS module.
 * API_BASE is resolved from ?bot= query param at runtime.
 * Replace with a hardcoded URL if the API moves to a dedicated host.
 */

const tg = window.Telegram.WebApp;

tg.ready();
tg.expand();

// ── Config ────────────────────────────────────────────────────────────────────

const params   = new URLSearchParams(location.search);
const BOT_TOKEN = params.get("bot") || "";
const API_BASE  = `/api/${BOT_TOKEN}`;

// ── Session state (persisted in sessionStorage across pages) ──────────────────

const STATE_KEY = "aria_booking";

function getState() {
  try { return JSON.parse(sessionStorage.getItem(STATE_KEY) || "{}"); }
  catch { return {}; }
}

function setState(patch) {
  sessionStorage.setItem(STATE_KEY, JSON.stringify({ ...getState(), ...patch }));
}

function clearState() {
  sessionStorage.removeItem(STATE_KEY);
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": tg.initData || "",
    ...(options.headers || {}),
  };
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

async function getCategories() {
  return apiFetch("/categories");
}

async function getServices(categoryId) {
  return apiFetch(`/services/${categoryId}`);
}

async function getSlots(date) {
  return apiFetch(`/slots/${date}`);
}

async function createBooking(payload) {
  return apiFetch("/booking", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function showError(elementId, message) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = message;
  el.classList.add("visible");
}

function hideError(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.classList.remove("visible");
}

function setLoading(containerId, isLoading) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (isLoading) {
    el.innerHTML = '<p class="loading">Загружаем…</p>';
  }
}

function navigate(page) {
  location.href = `${page}?bot=${encodeURIComponent(BOT_TOKEN)}`;
}

// ── Date / time helpers ───────────────────────────────────────────────────────

const WEEKDAY_RU = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"];
const MONTH_RU   = ["", "янв", "фев", "мар", "апр", "май", "июн",
                    "июл", "авг", "сен", "окт", "ноя", "дек"];

function formatDateLabel(isoDate) {
  const d = new Date(isoDate + "T00:00:00");
  return `${WEEKDAY_RU[d.getDay()]} ${d.getDate()} ${MONTH_RU[d.getMonth() + 1]}`;
}

// Export for use in inline scripts
window.Aria = {
  tg, BOT_TOKEN, API_BASE,
  getState, setState, clearState,
  getCategories, getServices, getSlots, createBooking,
  showError, hideError, setLoading,
  navigate, formatDateLabel,
};
