import { List, Section, Cell, Button, Placeholder } from '@telegram-apps/telegram-ui';
import type { BookingState } from '../types';

interface Props {
  booking: BookingState;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export default function ConfirmScreen({ booking }: Props) {
  return (
    <List>
      <Placeholder
        header="✅ Вы записаны!"
        description={`Номер записи: #${booking.bookingId}`}
      />

      <Section header="Детали записи">
        <Cell description={booking.category?.name}>
          {booking.service?.name}
        </Cell>
        <Cell description="Дата и время">
          {formatDate(booking.date!)} в {booking.time}
        </Cell>
        <Cell description="Клиент">
          {booking.clientName}
        </Cell>
      </Section>

      <Section footer="Вы получите напоминание за несколько часов до записи">
        <Button
          stretched
          size="l"
          mode="outline"
          onClick={() => window.Telegram?.WebApp?.close()}
        >
          Закрыть
        </Button>
      </Section>
    </List>
  );
}
