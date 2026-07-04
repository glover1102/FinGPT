import { Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { TickerSentimentResponse } from '../types'
import { POPULAR_TICKERS, getSentimentBadgeClass } from '../utils/helpers'
import LoadingSpinner from './LoadingSpinner'

interface BatchAnalysisProps {
  loading: boolean
  results: TickerSentimentResponse[]
  onAnalyzeAll: (tickers: string[]) => Promise<void>
}

export default function BatchAnalysis({ loading, results, onAnalyzeAll }: BatchAnalysisProps) {
  const [input, setInput] = useState('')
  const [selectedTickers, setSelectedTickers] = useState<string[]>(['AAPL', 'MSFT', 'TSLA'])

  const availableSuggestions = useMemo(
    () => POPULAR_TICKERS.filter((ticker) => ticker.includes(input.toUpperCase()) && !selectedTickers.includes(ticker)),
    [input, selectedTickers],
  )

  const addTicker = (ticker: string) => {
    if (!ticker || selectedTickers.includes(ticker)) {
      return
    }
    setSelectedTickers((prev) => [...prev, ticker])
    setInput('')
  }

  return (
    <section className="panel space-y-4" aria-label="Batch sentiment analysis">
      <div>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Batch Analysis</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">Compare sentiment across multiple stocks.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {selectedTickers.map((ticker) => (
          <button
            type="button"
            key={ticker}
            onClick={() => setSelectedTickers((prev) => prev.filter((item) => item !== ticker))}
            className="inline-flex items-center gap-1 rounded-full border border-indigo-400/50 px-3 py-1 text-xs text-indigo-200 hover:bg-indigo-500/20"
            aria-label={`Remove ${ticker}`}
          >
            {ticker} <Trash2 className="h-3.5 w-3.5" />
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          value={input}
          onChange={(event) => setInput(event.target.value.toUpperCase())}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && input.trim()) {
              addTicker(input.trim())
            }
          }}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          placeholder="Add ticker"
          aria-label="Add ticker to batch"
        />
        <button
          type="button"
          className="inline-flex items-center justify-center gap-1 rounded-lg border border-indigo-400/50 px-3 py-2 text-sm font-medium text-indigo-200 hover:bg-indigo-500/20"
          onClick={() => addTicker(input.trim())}
        >
          <Plus className="h-4 w-4" /> Add
        </button>
        <button
          type="button"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={loading || selectedTickers.length === 0}
          onClick={() => void onAnalyzeAll(selectedTickers)}
        >
          Analyze All
        </button>
      </div>

      {availableSuggestions.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {availableSuggestions.map((ticker) => (
            <button
              type="button"
              key={ticker}
              className="rounded-full border border-slate-600 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800"
              onClick={() => addTicker(ticker)}
            >
              {ticker}
            </button>
          ))}
        </div>
      ) : null}

      {loading ? <LoadingSpinner label="Analyzing batch tickers" /> : null}

      {results.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {results.map((result) => (
            <article key={result.ticker} className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">{result.ticker}</h3>
                <span className={`rounded-full border px-2 py-0.5 text-xs uppercase ${getSentimentBadgeClass(result.sentiment_label)}`}>
                  {result.sentiment_label}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Score: {result.sentiment_score.toFixed(3)}</p>
              <p className="text-sm text-slate-600 dark:text-slate-400">Confidence: {Math.round(result.confidence * 100)}%</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  )
}
