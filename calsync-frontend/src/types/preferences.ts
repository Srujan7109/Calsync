export type DayOfWeek = "MON" | "TUE" | "WED" | "THU" | "FRI" | "SAT" | "SUN";

export interface ParticipantPreferences {
  email: string;
  working_hours_start: string; // "HH:MM"
  working_hours_end: string; // "HH:MM"
  timezone: string; // IANA e.g. "Asia/Kolkata"
  preferred_days: DayOfWeek[];
  is_vip: boolean;
}
