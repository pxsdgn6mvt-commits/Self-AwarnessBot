import { useEffect, useState } from 'react';
import { List, Section, Cell, Placeholder, Spinner } from '@telegram-apps/telegram-ui';
import { getSlots } from '../api';

interface Props {
  tenantId: number;
  date: string;
  onSelect: (time: string) => void;
}

function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}.${m}.${y}`;
}

export default function TimeScreen({ tenantId, date, onSelect }: Props) {
  const [slots, setSlots]     = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState('');

  useEffect(() => {
    setLoading(true);
    setError('');
    getSlots(tenantId, date)
      .then(setSlots)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tenantId, date]);

  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (error) return <Placeholder description={error} />;

  if (!slots.length) {
    return (
      <Placeholder
        header="Нет свободных слотов"
        description="Вернитесь и выберите другую дату"
      />
    );
  }

  return (
    <List>
      <Section header={`Доступное время — ${formatDate(date)}`}>
        {slots.map(time => (
          <Cell key={time} onClick={() => onSelect(time)}>
            {time}
          </Cell>
        ))}
      </Section>
    </List>
  );
}
