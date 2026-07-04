import type { TickerSentimentResponse } from '../types'
import { formatPercent, formatTimestamp, getSentimentBadgeClass, toScoreWidth } from '../utils/helpers'

export default function SentimentCard({ sentiment }: { sentiment: TickerSentimentResponse | null }) {
  if (!sentiment) {
    return (
      <section className="panel">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Sentiment Summary</h2>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Analyze a ticker to view sentiment details.</p>
      </section>
    )
  }

  const sentimentClass = getSentimentBadgeClass(sentiment.sentiment_label)
  const scoreWidth = toScoreWidth(sentiment.sentiment_score)

  return (
    <section className="panel animate-fade-in" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-3xl font-extrabold tracking-tight text-slate-900 dark:text-slate-100">{sentiment.ticker}</h2>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase ${sentimentClass}`}>
          {sentiment.sentiment_label}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        <div className="flex justify-between text-sm text-slate-600 dark:text-slate-400">
          <span>Sentiment score</span>
          <span className="font-semibold text-slate-800 dark:text-slate-200">{sentiment.sentiment_score.toFixed(3)}</span>
        </div>
        <div className="h-3 rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="h-full rounded-full bg-gradient-to-r from-rose-500 via-amber-500 to-emerald-500 transition-all duration-300"
            style={{ width: `${scoreWidth}%` }}
            role="meter"
            aria-valuemin={-1}
            aria-valuemax={1}
            aria-valuenow={sentiment.sentiment_score}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>-1</span>
          <span>0</span>
          <span>+1</span>
        </div>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg bg-slate-100 p-3 dark:bg-slate-900/60">
          <dt className="text-slate-500 dark:text-slate-400">Confidence</dt>
          <dd className="font-semibold text-slate-900 dark:text-slate-100">{formatPercent(sentiment.confidence)}</dd>
        </div>
        <div className="rounded-lg bg-slate-100 p-3 dark:bg-slate-900/60">
          <dt className="text-slate-500 dark:text-slate-400">Articles analyzed</dt>
          <dd className="font-semibold text-slate-900 dark:text-slate-100">{sentiment.news_count}</dd>
        </div>
      </dl>

      <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">Updated: {formatTimestamp(sentiment.timestamp)}</p>
    </section>
  )
}
