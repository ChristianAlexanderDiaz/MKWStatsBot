/**
 * EmptyState - shown when there is no data to display (e.g. no guild selected).
 */

interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex items-center justify-center h-64">
      <p className="text-muted-foreground">{message}</p>
    </div>
  )
}
