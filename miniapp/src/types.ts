export interface ServiceItem {
  id: number;
  name: string;
  price: number | null;
  duration_minutes: number | null;
}

export interface Category {
  id: number;
  name: string;
  items: ServiceItem[];
}

export interface ServicesResponse {
  categories: Category[];
  working_days: number[];  // ISO weekdays: 1=Mon … 7=Sun
}

export interface BookingState {
  tenantId: number;
  category?: Category;
  service?: ServiceItem;
  date?: string;       // YYYY-MM-DD
  time?: string;       // HH:MM
  clientName?: string;
  bookingId?: number;
}

export type Screen = 'category' | 'service' | 'date' | 'time' | 'form' | 'confirm';
