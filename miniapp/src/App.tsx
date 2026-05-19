import { useState, useEffect, Component, ReactNode } from 'react';
import { AppRoot } from '@telegram-apps/telegram-ui';
import '@telegram-apps/telegram-ui/dist/styles.css';

import type { BookingState, Category, Screen } from './types';
import { getServices } from './api';
import CategoryScreen from './screens/CategoryScreen';
import ServiceScreen from './screens/ServiceScreen';
import DateScreen from './screens/DateScreen';
import TimeScreen from './screens/TimeScreen';
import FormScreen from './screens/FormScreen';
import ConfirmScreen from './screens/ConfirmScreen';

const twa = window.Telegram?.WebApp;

class ErrorBoundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 24, color: '#fff', background: '#1c1c1e', minHeight: '100vh' }}>
          <p>Не удалось загрузить приложение.</p>
          <p style={{ fontSize: 13, opacity: 0.6 }}>{this.state.error}</p>
          <button onClick={() => window.location.reload()} style={{ marginTop: 16, padding: '10px 20px' }}>
            Попробовать снова
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function safeAppearance(): 'light' | 'dark' {
  try { return twa?.colorScheme === 'dark' ? 'dark' : 'light'; }
  catch { return 'light'; }
}

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

  const [screen, setScreen]         = useState<Screen>('category');
  const [booking, setBooking]        = useState<BookingState>({ tenantId });
  const [categories, setCategories]  = useState<Category[]>([]);
  const [catsLoading, setCatsLoading] = useState(true);
  const [catsError, setCatsError]    = useState('');

  useEffect(() => {
    twa?.ready();
    twa?.expand();
  }, []);

  useEffect(() => {
    getServices(tenantId)
      .then(setCategories)
      .catch((e: Error) => setCatsError(e.message))
      .finally(() => setCatsLoading(false));
  }, [tenantId]);

  // Back button wiring
  useEffect(() => {
    if (screen === 'category' || screen === 'confirm') {
      twa?.BackButton.hide();
    } else {
      twa?.BackButton.show();
    }
    const handler = () => setScreen(s => PREV[s]);
    twa?.BackButton.onClick(handler);
    return () => twa?.BackButton.offClick(handler);
  }, [screen]);

  const go = (s: Screen) => setScreen(s);

  return (
    <ErrorBoundary>
    <AppRoot appearance={safeAppearance()} platform="base">
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
    </AppRoot>
    </ErrorBoundary>
  );
}
