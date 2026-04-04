import { Loader2 } from "lucide-react";

export default function LoadingSpinner({
  className,
  size = 24,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <Loader2
      className={`animate-spin text-[var(--color-accent)] ${className}`}
      size={size}
    />
  );
}
