import { List, Cell, Section } from '@telegram-apps/telegram-ui';
import type { Category, ServiceItem } from '../types';

interface Props {
  category: Category;
  onSelect: (svc: ServiceItem) => void;
}

function formatMeta(item: ServiceItem): string | undefined {
  const parts: string[] = [];
  if (item.price != null)            parts.push(`${item.price} ₽`);
  if (item.duration_minutes != null) parts.push(`${item.duration_minutes} мин`);
  return parts.length ? parts.join(' · ') : undefined;
}

export default function ServiceScreen({ category, onSelect }: Props) {
  return (
    <List>
      <Section header={category.name}>
        {category.items.map(item => (
          <Cell
            key={item.id}
            description={formatMeta(item)}
            onClick={() => onSelect(item)}
          >
            {item.name}
          </Cell>
        ))}
      </Section>
    </List>
  );
}
