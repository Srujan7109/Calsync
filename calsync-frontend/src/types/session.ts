export type SessionStatus =
  | "AWAITING_REPLIES"
  | "READY_TO_COMPUTE"
  | "COMPUTING"
  | "BOOKED"
  | "NO_OVERLAP"
  | "EXPIRED"
  | "CANCELLED";

export interface TimeSlot {
  start: string; // ISO 8601 UTC
  end: string; // ISO 8601 UTC
  confidence?: number;
}

export interface Session {
  session_id: string;
  thread_id: string;
  meeting_title: string;
  organizer: string;
  participants: string[];
  participants_replied: string[];
  participants_pending: string[];
  status: SessionStatus;
  collected_slots: Record<string, TimeSlot[]>;
  booked_slot: TimeSlot | null;
  booked_event_id: string | null;
  booked_event_link: string | null;
  thread_summary: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionListResponse {
  sessions: Session[];
  total: number;
  has_more: boolean;
}

export interface OverridePayload {
  action: "CANCEL" | "RESCHEDULE" | "FORCE_BOOK";
  reason: string;
  new_slot?: TimeSlot;
}
