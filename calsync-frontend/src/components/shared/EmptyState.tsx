import { ReactNode } from "react";

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export default function EmptyState({
  icon,
  title,
  description,
  action,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/50">
      <div className="text-[var(--color-muted)] mb-4 bg-[var(--color-surface)] p-4 rounded-full">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-[var(--color-text-strong)] mb-2">
        {title}
      </h3>
      <p className="text-[var(--color-muted)] max-w-sm mb-6">{description}</p>

      {action && (
        <button
          onClick={action.onClick}
          className="px-4 py-2 bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] text-white rounded-md transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
