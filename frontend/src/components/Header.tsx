import { ExternalLink, Moon, Sun } from 'lucide-react'

interface HeaderProps {
  darkMode: boolean
  onToggleDarkMode: () => void
  sidebarOpen: boolean
  onToggleSidebar: () => void
}

export default function Header({
  darkMode,
  onToggleDarkMode,
  sidebarOpen,
  onToggleSidebar,
}: HeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/20 bg-white/80 px-4 py-4 backdrop-blur dark:border-slate-700/50 dark:bg-slate-950/70 md:px-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            aria-label="Toggle sidebar"
            onClick={onToggleSidebar}
            className="rounded-md border border-slate-300/60 px-3 py-1 text-sm text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800 lg:hidden"
          >
            {sidebarOpen ? 'Close' : 'Menu'}
          </button>
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-indigo-500">FinGPT</p>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">FinGPT Sentiment</h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <a
            href="https://fingpt-production-c5b4.up.railway.app/docs"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-md border border-slate-300/60 px-3 py-2 text-sm text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            API Docs <ExternalLink className="h-4 w-4" />
          </a>
          <button
            type="button"
            aria-label="Toggle dark mode"
            onClick={onToggleDarkMode}
            className="rounded-md border border-slate-300/60 p-2 text-slate-700 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </header>
  )
}
