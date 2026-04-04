import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow } from "date-fns";

// shadcn/ui utility
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Format recent timestamps as relative ("3 minutes ago"), older as absolute ("Jan 6, 2025 at 9:30 AM")
export function formatTimestamp(utcString: string): string {
  if (!utcString) return "—";

  const date = new Date(utcString);
  const now = new Date();
  const diffInHours = (now.getTime() - date.getTime()) / (1000 * 60 * 60);

  if (diffInHours < 24) {
    return formatDistanceToNow(date, { addSuffix: true });
  }
  return format(date, "MMM d, yyyy 'at' h:mm a");
}

// Format time slots: "Mon, Jan 6 • 9:30 AM - 10:30 AM IST"
export function formatTimeSlot(
  start: string,
  end: string,
  timezone?: string,
): string {
  if (!start || !end) return "—";

  const startDate = new Date(start);
  const endDate = new Date(end);

  const dateStr = format(startDate, "EEE, MMM d");
  const timeStr = `${format(startDate, "h:mm a")} - ${format(endDate, "h:mm a")}`;

  return `${dateStr} • ${timeStr} ${timezone ? timezone : "UTC"}`;
}

// Truncate Session ID to last 8 characters
export function formatSessionId(id: string): string {
  if (!id) return "—";
  return `sess_${id.slice(-8)}`;
}
