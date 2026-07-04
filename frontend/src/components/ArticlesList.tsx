import { getSentimentBadgeClass } from '../utils/helpers'

interface ArticlesListProps {
  articles: string[]
  sentimentLabel: string
}

export default function ArticlesList({ articles, sentimentLabel }: ArticlesListProps) {
  return (
    <section className="panel">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">News Headlines</h2>
        <span className={`rounded-full border px-2 py-0.5 text-xs uppercase ${getSentimentBadgeClass(sentimentLabel)}`}>
          {sentimentLabel}
        </span>
      </div>

      {articles.length === 0 ? (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">No articles available for this ticker.</p>
      ) : (
        <ul className="mt-3 max-h-72 space-y-3 overflow-y-auto pr-1" aria-label="Analyzed articles">
          {articles.slice(0, 5).map((headline) => (
            <li
              key={headline}
              className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700 transition duration-200 hover:border-indigo-400 hover:shadow-sm dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-200"
            >
              {headline}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
