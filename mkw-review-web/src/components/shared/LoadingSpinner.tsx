/**
 * LoadingSpinner - centred spinner used on data-loading screens.
 * Accepts an optional label shown below the spinner.
 */

interface LoadingSpinnerProps {
  label?: string
}

export function LoadingSpinner({ label = "Loading..." }: LoadingSpinnerProps) {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4" />
        <p className="text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}
