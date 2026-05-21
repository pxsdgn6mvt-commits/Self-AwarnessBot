import { useState } from 'react';
import './DateScreen.css';

interface Props {
  workingDays: number[];  // ISO weekdays: 1=Mon … 7=Sun
  onSelect: (date: string) => void;
}

const MONTHS = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];
const DAYS = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// JS getDay(): 0=Sun,1=Mon…6=Sat; ISO: 1=Mon…7=Sun → convert via (jsDay || 7)
function isWorkingDay(d: Date, workingDays: number[]): boolean {
  const jsDay = d.getDay();
  const isoDay = jsDay === 0 ? 7 : jsDay;
  return workingDays.includes(isoDay);
}

export default function DateScreen({ workingDays, onSelect }: Props) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [view, setView] = useState(
    new Date(today.getFullYear(), today.getMonth(), 1),
  );

  const year  = view.getFullYear();
  const month = view.getMonth();

  const firstWeekday = (new Date(year, month, 1).getDay() + 6) % 7; // 0=Mon
  const daysInMonth  = new Date(year, month + 1, 0).getDate();

  const cells: (Date | null)[] = [
    ...(Array(firstWeekday).fill(null) as null[]),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(year, month, i + 1)),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const canGoPrev =
    view > new Date(today.getFullYear(), today.getMonth(), 1);

  return (
    <div className="date-screen">
      <div className="cal-nav">
        <button
          className="cal-nav-btn"
          disabled={!canGoPrev}
          onClick={() => setView(new Date(year, month - 1, 1))}
        >
          ‹
        </button>
        <span className="cal-month-label">{MONTHS[month]} {year}</span>
        <button
          className="cal-nav-btn"
          onClick={() => setView(new Date(year, month + 1, 1))}
        >
          ›
        </button>
      </div>

      <div className="cal-grid">
        {DAYS.map(d => (
          <div key={d} className="cal-weekday">{d}</div>
        ))}

        {cells.map((d, i) => {
          if (!d) return <div key={i} />;
          const past        = d < today;
          const nonWorking  = !isWorkingDay(d, workingDays);
          const disabled    = past || nonWorking;
          const isToday     = toISO(d) === toISO(today);
          return (
            <button
              key={i}
              className={[
                'cal-day',
                disabled  ? 'cal-day--past'    : 'cal-day--available',
                isToday   ? 'cal-day--today'   : '',
              ].join(' ').trim()}
              disabled={disabled}
              onClick={() => !disabled && onSelect(toISO(d))}
            >
              {d.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}
