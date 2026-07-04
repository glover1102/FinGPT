export default function LoadingSpinner({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="inline-flex items-center gap-2 text-sm text-slate-300" role="status" aria-live="polite">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-indigo-400" />
      {label}
    </div>
  )
}
