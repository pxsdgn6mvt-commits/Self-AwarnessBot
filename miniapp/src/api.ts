import type { Category } from './types';

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '';

function initData(): string {
  return window.Telegram?.WebApp?.initData ?? '';
}

export async function getServices(tenantId: number): Promise<Category[]> {
  const r = await fetch(`${BASE}/api/services?tenant_id=${tenantId}`);
  if (!r.ok) throw new Error('Не удалось загрузить услуги');
  return r.json() as Promise<Category[]>;
}

export async function getSlots(tenantId: number, date: string): Promise<string[]> {
  const r = await fetch(`${BASE}/api/slots?tenant_id=${tenantId}&date=${date}`);
  if (!r.ok) throw new Error('Не удалось загрузить время');
  return r.json() as Promise<string[]>;
}

export async function createBooking(params: {
  tenantId: number;
  serviceName: string;
  date: string;
  time: string;
  clientName: string;
}): Promise<number> {
  const r = await fetch(`${BASE}/api/bookings`, {
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
