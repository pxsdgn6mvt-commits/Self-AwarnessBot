// API_BASE injected via <meta name="api-base">
const _metaBase = document.querySelector('meta[name="api-base"]');
const _API_ROOT = _metaBase ? _metaBase.content : '';

const tg = window.Telegram?.WebApp;
if (tg) tg.ready();

function getBotToken() {
  return new URLSearchParams(window.location.search).get('bot') || '';
}

function getParam(key) {
  return new URLSearchParams(window.location.search).get(key) || '';
}

function apiBase() {
  return `${_API_ROOT}/api/${getBotToken()}`;
}

async function apiFetch(path, opts = {}) {
  const initData = tg?.initData || '';
  const res = await fetch(apiBase() + path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData,
      ...(opts.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// ── index.html ────────────────────────────────────────────────────────────────

async function loadCategories() {
  const list = document.getElementById('category-list');
  if (!list) return;
  try {
    const cats = await apiFetch('/categories');
    if (!cats.length) {
      list.innerHTML = '<p style="color:var(--tg-hint)">Категории не настроены</p>';
      return;
    }
    list.innerHTML = cats.map(c => `
      <div class="card" onclick="gotoBooking(${c.id}, '${esc(c.name)}')">
        <span>${esc(c.name)}</span>
        <span class="arrow">›</span>
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `<p class="error">Ошибка загрузки: ${e.message}</p>`;
  }
}

function gotoBooking(catId, catName) {
  const p = new URLSearchParams(window.location.search);
  p.set('cat', catId);
  p.set('catName', catName);
  window.location.href = `booking.html?${p}`;
}

// ── booking.html ──────────────────────────────────────────────────────────────

async function loadServices() {
  const catId = getParam('cat');
  const list = document.getElementById('service-list');
  if (!list || !catId) return;

  const title = document.getElementById('cat-title');
  if (title) title.textContent = getParam('catName');

  try {
    const items = await apiFetch(`/services/${catId}`);
    list.innerHTML = items.map(s => `
      <div class="pill" data-id="${s.id}" data-name="${esc(s.name)}" onclick="selectService(this)">
        ${esc(s.name)}${s.price ? ` — ${s.price}₽` : ''}
      </div>`).join('');
  } catch (e) {
    list.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function selectService(el) {
  document.querySelectorAll('#service-list .pill').forEach(p => p.classList.remove('selected'));
  el.classList.add('selected');
  window._selectedService = { id: el.dataset.id, name: el.dataset.name };
  updateSlots();
}

async function updateSlots() {
  const date = document.getElementById('date-input')?.value;
  const slotGrid = document.getElementById('slot-grid');
  if (!slotGrid || !date) return;
  slotGrid.innerHTML = '<p style="color:var(--tg-hint)">Загрузка...</p>';
  try {
    const data = await apiFetch(`/slots/${date}`);
    slotGrid.innerHTML = data.slots.map(s => `
      <div class="pill" data-slot="${s}" onclick="selectSlot(this)">${s}</div>`).join('');
  } catch (e) {
    slotGrid.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function selectSlot(el) {
  document.querySelectorAll('#slot-grid .pill').forEach(p => p.classList.remove('selected'));
  el.classList.add('selected');
  window._selectedSlot = el.dataset.slot;
}

function gotoConfirm() {
  const date = document.getElementById('date-input')?.value;
  if (!window._selectedService) { alert('Выберите услугу'); return; }
  if (!date) { alert('Выберите дату'); return; }
  if (!window._selectedSlot) { alert('Выберите время'); return; }

  const scheduledAt = `${date}T${window._selectedSlot}:00`;
  const p = new URLSearchParams(window.location.search);
  p.set('service', window._selectedService.name);
  p.set('scheduledAt', scheduledAt);
  window.location.href = `confirm.html?${p}`;
}

// ── confirm.html ──────────────────────────────────────────────────────────────

function fillSummary() {
  const service = getParam('service');
  const at = getParam('scheduledAt');
  const el = document.getElementById('booking-summary');
  if (!el) return;
  el.innerHTML = `<p><strong>Услуга:</strong> ${esc(service)}</p>
    <p><strong>Время:</strong> ${esc(at.replace('T', ' ').slice(0, 16))}</p>`;
}

async function submitBooking() {
  const btn = document.getElementById('submit-btn');
  const errEl = document.getElementById('err');
  const name = document.getElementById('client-name')?.value?.trim();
  const phone = document.getElementById('client-phone')?.value?.trim();

  if (!name) { if (errEl) errEl.textContent = 'Введите имя'; return; }
  if (errEl) errEl.textContent = '';
  if (btn) btn.disabled = true;

  try {
    await apiFetch('/booking', {
      method: 'POST',
      body: JSON.stringify({
        client_name: name,
        client_phone: phone || null,
        service: getParam('service'),
        scheduled_at: getParam('scheduledAt'),
      }),
    });
    document.getElementById('form-section').style.display = 'none';
    document.getElementById('success-section').style.display = 'block';
    tg?.close();
  } catch (e) {
    if (errEl) errEl.textContent = `Ошибка: ${e.message}`;
    if (btn) btn.disabled = false;
  }
}

// ── utils ─────────────────────────────────────────────────────────────────────

function esc(str) {
  return String(str).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
