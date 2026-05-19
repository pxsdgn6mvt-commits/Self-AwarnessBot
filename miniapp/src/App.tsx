import { useState, useEffect } from 'react';
import type { BookingState, Category, Screen } from './types';
import { getServices } from './api';
import CategoryScreen from './screens/CategoryScreen';
import ServiceScreen from './screens/ServiceScreen';
import DateScreen from './screens/DateScreen';
import TimeScreen from './screens/TimeScreen';
import FormScreen from './screens/FormScreen';
import ConfirmScreen from './screens/ConfirmScreen';

const twa = window.Telegram?.WebApp;

const PREV: Record<Screen, Screen> = {
  category: 'category',
  service:  'category',
  date:     'service',
  time:     'date',
  form:     'time',
  confirm:  'form',
};

export default function App() {
  const tenantId = parseInt(
    new URLSearchParams(window.location.search).get('tenant_id') ?? '1',
  );

  const [screen, setScreen]          = useState<Screen>('category');
  const [booking, setBooking]         = useState<BookingState>({ tenantId });
  const [categories, setCategories]   = useState<Category[]>([]);
  const [catsLoading, setCatsLoading] = useState(true);
  const [catsError, setCatsError]     = useState('');

  useEffect(() => {
    try { twa?.ready(); twa?.expand(); } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    getServices(tenantId)
      .then(setCategories)
      .catch((e: Error) => setCatsError(e.message))
      .finally(() => setCatsLoading(false));
  }, [tenantId]);

  useEffect(() => {
    try {
      if (screen === 'category' || screen === 'confirm') {
        twa?.BackButton.hide();
      } else {
        twa?.BackButton.show();
      }
      const handler = () => setScreen(s => PREV[s]);
      twa?.BackButton.onClick(handler);
      return () => twa?.BackButton.offClick(handler);
    } catch { /* ignore */ }
  }, [screen]);

  const go = (s: Screen) => setScreen(s);

  return (
    <div style={{ minHeight: '100vh', background: 'var(--tg-theme-bg-color, #fff)' }}>
      {screen === 'category' && (
        <CategoryScreen
          categories={categories}
          loading={catsLoading}
          error={catsError}
          onSelect={cat => {
            setBooking(b => ({ ...b, category: cat, service: undefined, date: undefined, time: undefined }));
            go('service');
          }}
        />
      )}

      {screen === 'service' && booking.category && (
        <ServiceScreen
          category={booking.category}
          onSelect={svc => {
            setBooking(b => ({ ...b, service: svc, date: undefined, time: undefined }));
            go('date');
          }}
        />
      )}

      {screen === 'date' && (
        <DateScreen
          onSelect={date => {
            setBooking(b => ({ ...b, date, time: undefined }));
            go('time');
          }}
        />
      )}

      {screen === 'time' && (
        <TimeScreen
          tenantId={tenantId}
          date={booking.date!}
          onSelect={time => {
            setBooking(b => ({ ...b, time }));
            go('form');
          }}
        />
      )}

      {screen === 'form' && (
        <FormScreen
          booking={booking}
          onSubmit={(clientName, bookingId) => {
            setBooking(b => ({ ...b, clientName, bookingId }));
            go('confirm');
          }}
        />
      )}

      {screen === 'confirm' && (
        <ConfirmScreen booking={booking} />
      )}
    </div>
  );
}
