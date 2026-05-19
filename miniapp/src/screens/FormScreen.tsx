import { useState } from 'react';
import { List, Section, Cell, Button } from '../ui';
import type { BookingState } from '../types';
import { createBooking } from '../api';
import './FormScreen.css';

interface Props {
  booking: BookingState;
  onSubmit: (clientName: string, bookingId: number) => void;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export default function FormScreen({ booking, onSubmit }: Props) {
  const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
  const defaultName = tgUser
    ? [tgUser.first_name, tgUser.last_name].filter(Boolean).join(' ')
    : '';

  const [name, setName]       = useState(defaultName);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState('');

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed) { setError('Введите ваше имя'); return; }
    setLoading(true);
    setError('');
    try {
      const bookingId = await createBooking({
        tenantId:    booking.tenantId,
        serviceName: booking.service!.name,
        date:        booking.date!,
        time:        booking.time!,
        clientName:  trimmed,
      });
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred('success');
      onSubmit(trimmed, bookingId);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка записи');
    } finally {
      setLoading(false);
    }
  };

  return (
    <List>
      <Section header="Ваша запись">
        <Cell description={booking.category?.name}>
          {booking.service?.name}
        </Cell>
        <Cell description="Дата и время">
          {formatDate(booking.date!)} в {booking.time}
        </Cell>
      </Section>

      <Section header="Ваше имя" footer={error || undefined}>
        <div className="name-input-wrap">
          <input
            className={`name-input ${error ? 'name-input--error' : ''}`}
            type="text"
            placeholder="Имя"
            value={name}
            onChange={e => { setName(e.target.value); setError(''); }}
            disabled={loading}
            autoFocus
          />
        </div>
      </Section>

      <Section>
        <Button
          stretched
          size="l"
          disabled={loading || !name.trim()}
          onClick={handleSubmit}
        >
          {loading ? 'Записываю…' : 'Записаться'}
        </Button>
      </Section>
    </List>
  );
}
