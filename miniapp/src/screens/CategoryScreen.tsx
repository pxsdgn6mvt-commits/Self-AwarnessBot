import { List, Cell, Section, Placeholder, Spinner } from '@telegram-apps/telegram-ui';
import type { Category } from '../types';

interface Props {
  categories: Category[];
  loading: boolean;
  error: string;
  onSelect: (cat: Category) => void;
}

export default function CategoryScreen({ categories, loading, error, onSelect }: Props) {
  if (loading) {
    return (
      <Placeholder>
        <Spinner size="m" />
      </Placeholder>
    );
  }

  if (error) {
    return <Placeholder description={error} />;
  }

  if (!categories.length) {
    return <Placeholder description="Услуги пока не настроены" />;
  }

  return (
    <List>
      <Section header="Выберите категорию">
        {categories.map(cat => (
          <Cell
            key={cat.id}
            description={`${cat.items.length} услуг`}
            onClick={() => onSelect(cat)}
          >
            {cat.name}
          </Cell>
        ))}
      </Section>
    </List>
  );
}
