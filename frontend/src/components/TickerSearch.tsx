import { Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { POPULAR_TICKERS } from '../utils/helpers'
import LoadingSpinner from './LoadingSpinner'

interface TickerSearchProps {
  loading: boolean
  onAnalyze: (ticker: string) => Promise<void>
}

export default function TickerSearch({ loading, onAnalyze }: TickerSearchProps) {
  const [value, setValue] = useState('AAPL')
  const [query, setQuery] = useState('AAPL')

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(value), 250)
    return () => window.clearTimeout(timer)
  }, [value])

  const suggestions = useMemo(
    () => POPULAR_TICKERS.filter((ticker) => ticker.includes(query.toUpperCase())).slice(0, 8),
    [query],
  )

  return (
    <section className="panel space-y-4" aria-label="Ticker analysis">
      <div>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Ticker Sentiment</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">Search a ticker and analyze latest sentiment.</p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="ticker-input" className="sr-only">
          Ticker symbol
        </label>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            id="ticker-input"
            className="w-full rounded-lg border border-slate-300 bg-white px-9 py-2 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            placeholder="Enter ticker (e.g., AAPL)"
            value={value}
            onChange={(event) => setValue(event.target.value.toUpperCase())}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && value.trim()) {
                void onAnalyze(value.trim())
              }
            }}
            autoComplete="off"
          />
        </div>
        <button
          type="button"
          onClick={() => void onAnalyze(value.trim())}
          disabled={loading || !value.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </div>

      <div className="flex flex-wrap gap-2" aria-label="Popular ticker suggestions">
        {suggestions.map((ticker) => (
          <button
            key={ticker}
            type="button"
            className="rounded-full border border-indigo-400/50 px-3 py-1 text-xs font-medium text-indigo-300 transition hover:bg-indigo-500/20"
            onClick={() => {
              setValue(ticker)
              void onAnalyze(ticker)
            }}
          >
            {ticker}
          </button>
        ))}
      </div>

      {loading ? <LoadingSpinner label="Fetching sentiment data" /> : null}
    </section>
  )
}
