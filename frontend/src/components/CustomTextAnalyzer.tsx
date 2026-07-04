import { useState } from 'react'
import type { SentimentResponse } from '../types'
import { formatPercent, getSentimentBadgeClass } from '../utils/helpers'
import LoadingSpinner from './LoadingSpinner'

interface CustomTextAnalyzerProps {
  loading: boolean
  result: SentimentResponse | null
  onAnalyze: (text: string, ticker?: string) => Promise<void>
}

export default function CustomTextAnalyzer({ loading, result, onAnalyze }: CustomTextAnalyzerProps) {
  const [text, setText] = useState('')
  const [ticker, setTicker] = useState('')

  return (
    <section className="panel space-y-4" aria-label="Custom text sentiment analyzer">
      <div>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Custom Text Analyzer</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">Analyze your own financial text with optional ticker context.</p>
      </div>

      <div className="space-y-3">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300" htmlFor="custom-text">
          Financial text
        </label>
        <textarea
          id="custom-text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={4}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          placeholder="Paste earnings news, analyst note, or market commentary..."
        />
        <input
          value={ticker}
          onChange={(event) => setTicker(event.target.value.toUpperCase())}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          placeholder="Optional ticker (e.g., AAPL)"
          aria-label="Optional ticker for text analysis"
        />
        <button
          type="button"
          disabled={!text.trim() || loading}
          onClick={() => void onAnalyze(text.trim(), ticker.trim() || undefined)}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Analyze Text
        </button>
      </div>

      {loading ? <LoadingSpinner label="Analyzing custom text" /> : null}

      {result ? (
        <article className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/60">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">Result</h3>
            <span className={`rounded-full border px-2 py-0.5 text-xs uppercase ${getSentimentBadgeClass(result.sentiment_label)}`}>
              {result.sentiment_label}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Score: {result.sentiment_score.toFixed(3)}</p>
          <p className="text-sm text-slate-600 dark:text-slate-400">Confidence: {formatPercent(result.confidence)}</p>
        </article>
      ) : null}
    </section>
  )
}
