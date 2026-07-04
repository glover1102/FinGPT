import { Activity, BarChart3, Newspaper, Sparkles, TextCursorInput } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AxiosError } from 'axios'
import { analyzeSentiment, getBatchSentiment, getHealth, getTickerSentiment } from '../services/api'
import type { HealthResponse, SentimentResponse, TickerSentimentResponse } from '../types'
import ArticlesList from './ArticlesList'
import BatchAnalysis from './BatchAnalysis'
import CustomTextAnalyzer from './CustomTextAnalyzer'
import Header from './Header'
import SentimentCard from './SentimentCard'
import SentimentChart from './SentimentChart'
import TickerSearch from './TickerSearch'

const NAV_ITEMS = [
  { id: 'ticker', label: 'Ticker Search', icon: Activity },
  { id: 'chart', label: 'Breakdown Chart', icon: BarChart3 },
  { id: 'news', label: 'News Articles', icon: Newspaper },
  { id: 'batch', label: 'Batch Analysis', icon: Sparkles },
  { id: 'custom', label: 'Custom Text', icon: TextCursorInput },
]

export default function Dashboard() {
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('fingpt-theme') !== 'light')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [currentSentiment, setCurrentSentiment] = useState<TickerSentimentResponse | null>(null)
  const [batchResults, setBatchResults] = useState<TickerSentimentResponse[]>([])
  const [customResult, setCustomResult] = useState<SentimentResponse | null>(null)
  const [loadingTicker, setLoadingTicker] = useState(false)
  const [loadingBatch, setLoadingBatch] = useState(false)
  const [loadingCustom, setLoadingCustom] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode)
    localStorage.setItem('fingpt-theme', darkMode ? 'dark' : 'light')
  }, [darkMode])

  useEffect(() => {
    void getHealth().then(setHealth).catch(() => undefined)
  }, [])

  const parseError = useCallback((value: unknown): string => {
    if (value instanceof AxiosError) {
      return value.response?.data?.detail ?? value.message
    }
    return 'Something went wrong. Please try again.'
  }, [])

  const handleTickerAnalyze = useCallback(
    async (ticker: string) => {
      if (!ticker) {
        return
      }
      setLoadingTicker(true)
      setError('')
      try {
        const result = await getTickerSentiment(ticker)
        setCurrentSentiment(result)
      } catch (value) {
        setError(parseError(value))
      } finally {
        setLoadingTicker(false)
      }
    },
    [parseError],
  )

  const handleBatchAnalyze = useCallback(
    async (tickers: string[]) => {
      setLoadingBatch(true)
      setError('')
      try {
        const result = await getBatchSentiment(tickers)
        setBatchResults(result)
      } catch (value) {
        setError(parseError(value))
      } finally {
        setLoadingBatch(false)
      }
    },
    [parseError],
  )

  const handleCustomAnalyze = useCallback(
    async (text: string, ticker?: string) => {
      setLoadingCustom(true)
      setError('')
      try {
        const result = await analyzeSentiment({ text, ticker })
        setCustomResult(result)
      } catch (value) {
        setError(parseError(value))
      } finally {
        setLoadingCustom(false)
      }
    },
    [parseError],
  )

  const statusText = useMemo(() => {
    if (!health) {
      return 'Checking API health...'
    }
    return health.status === 'healthy' ? 'API healthy' : 'API unavailable'
  }, [health])

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-100 to-indigo-100 text-slate-900 transition-colors dark:from-slate-950 dark:to-slate-900 dark:text-slate-100">
      <Header
        darkMode={darkMode}
        onToggleDarkMode={() => setDarkMode((prev) => !prev)}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
      />

      <div className="mx-auto flex max-w-7xl gap-4 px-4 py-6 md:px-6">
        <aside
          className={`fixed inset-y-[73px] left-0 z-20 w-64 border-r border-slate-200/70 bg-white/95 p-4 backdrop-blur transition-transform dark:border-slate-800 dark:bg-slate-950/95 lg:static lg:translate-x-0 ${
            sidebarOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
          aria-label="Sidebar navigation"
        >
          <p className="mb-4 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Dashboard</p>
          <nav className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                onClick={() => setSidebarOpen(false)}
                className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-700 transition hover:bg-indigo-100 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </a>
            ))}
          </nav>

          <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-900/60">
            <p className="font-semibold">Status</p>
            <p className="mt-1 text-slate-600 dark:text-slate-400">{statusText}</p>
          </div>
        </aside>

        <main className="flex-1 space-y-4 lg:ml-0">
          {error ? (
            <div className="rounded-lg border border-rose-300 bg-rose-100 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-200">
              {error}
            </div>
          ) : null}

          <section id="ticker">
            <TickerSearch loading={loadingTicker} onAnalyze={handleTickerAnalyze} />
          </section>

          <div className="grid gap-4 xl:grid-cols-2">
            <section id="chart">
              <SentimentCard sentiment={currentSentiment} />
            </section>
            <SentimentChart score={currentSentiment?.sentiment_score ?? 0} />
          </div>

          <section id="news">
            <ArticlesList
              articles={currentSentiment?.articles_analyzed ?? []}
              sentimentLabel={currentSentiment?.sentiment_label ?? 'neutral'}
            />
          </section>

          <section id="batch">
            <BatchAnalysis loading={loadingBatch} results={batchResults} onAnalyzeAll={handleBatchAnalyze} />
          </section>

          <section id="custom">
            <CustomTextAnalyzer loading={loadingCustom} result={customResult} onAnalyze={handleCustomAnalyze} />
          </section>
        </main>
      </div>
    </div>
  )
}
