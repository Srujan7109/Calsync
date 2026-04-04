export interface CalendarEvent {
  event_id: string;
  title: string;
  start: string;
  end: string;
  attendees: { email: string; status: string }[];
  event_link: string;
  description: string;
  coordinated_by_calsync: boolean;
  session_id: string | null;
  meet_link: string | null;
}

export interface HeatmapSlot {
  free_count: number;
  total: number;
  all_free: boolean;
  participants_free: string[];
}

export type AvailabilityHeatmap = Record<string, HeatmapSlot>;
