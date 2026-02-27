/**
 * EmptyState - shown when there is no data to display (e.g. no guild selected).
 */

interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div
      className="flex items-center justify-center h-64"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <p className="text-muted-foreground">{message}</p>
    </div>
  )
}
