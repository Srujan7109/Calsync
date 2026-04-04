import { SessionStatus } from "@/types/session";
import {
  Clock,
  Cpu,
  CheckCircle2,
  AlertTriangle,
  TimerOff,
  XCircle,
  Loader2,
} from "lucide-react";

export default function StatusBadge({ status }: { status: SessionStatus }) {
  const config = {
    AWAITING_REPLIES: {
      color:
        "bg-[var(--color-warning)]/10 text-[var(--color-warning)] border-[var(--color-warning)]/20",
      icon: Clock,
      label: "Awaiting Replies",
    },
    READY_TO_COMPUTE: {
      color:
        "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/20",
      icon: Cpu,
      label: "Ready to Compute",
    },
    COMPUTING: {
      color:
        "bg-[var(--color-accent)]/10 text-[var(--color-accent)] border-[var(--color-accent)]/20",
      icon: Loader2,
      label: "Computing...",
    },
    BOOKED: {
      color:
        "bg-[var(--color-success)]/10 text-[var(--color-success)] border-[var(--color-success)]/20",
      icon: CheckCircle2,
      label: "Booked",
    },
    NO_OVERLAP: {
      color:
        "bg-[var(--color-error)]/10 text-[var(--color-error)] border-[var(--color-error)]/20",
      icon: AlertTriangle,
      label: "No Overlap",
    },
    EXPIRED: {
      color:
        "bg-[var(--color-muted)]/10 text-[var(--color-muted)] border-[var(--color-muted)]/20",
      icon: TimerOff,
      label: "Expired",
    },
    CANCELLED: {
      color:
        "bg-[var(--color-muted)]/10 text-[var(--color-muted)] border-[var(--color-muted)]/20",
      icon: XCircle,
      label: "Cancelled",
    },
  }[status];

  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${config.color}`}
    >
      <Icon
        className={status === "COMPUTING" ? "animate-spin" : ""}
        size={14}
      />
      {config.label}
    </span>
  );
}
