import type { Category } from './types';

const BASE = ((import.meta.env.VITE_API_BASE as string | undefined) ?? '').replace(/^<|>$/g, '').replace(/\/$/, '');

async function fetchWithRetry(url: string, options?: RequestInit, retries = 2): Promise<Response> {
  for (let i = 0; i < retries; i++) {
    try {
      const r = await fetch(url, options);
      return r;
    } catch (e) {
      if (i === retries - 1) throw e;
      await new Promise(res => setTimeout(res, 1500));
    }
  }
  throw new Error('Network error');
}

function initData(): string {
  return window.Telegram?.WebApp?.initData ?? '';
}

export async function getServices(tenantId: number): Promise<Category[]> {
  const url = `${BASE}/api/services?tenant_id=${tenantId}`;
  try {
    const r = await fetchWithRetry(url);
    if (!r.ok) throw new Error(`Сервер ответил ${r.status}`);
    return r.json() as Promise<Category[]>;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(`${msg} (${url})`);
  }
}

export async function getSlots(tenantId: number, date: string): Promise<string[]> {
  const url = `${BASE}/api/slots?tenant_id=${tenantId}&date=${date}`;
  try {
    const r = await fetchWithRetry(url);
    if (!r.ok) throw new Error(`Сервер ответил ${r.status}`);
    return r.json() as Promise<string[]>;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(`${msg} (${url})`);
  }
}

export async function createBooking(params: {
  tenantId: number;
  serviceName: string;
  date: string;
  time: string;
  clientName: string;
}): Promise<number> {
  const r = await fetchWithRetry(`${BASE}/api/bookings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tenant_id: params.tenantId,
      service: params.serviceName,
      date: params.date,
      time: params.time,
      client_name: params.clientName,
      initData: initData(),
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({})) as { error?: string };
    throw new Error(err.error ?? 'Ошибка записи');
  }
  const data = await r.json() as { booking_id: number };
  return data.booking_id;
}
