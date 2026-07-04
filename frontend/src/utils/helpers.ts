import type { SentimentLabel } from '../types'

export const POPULAR_TICKERS = ['AAPL', 'MSFT', 'TSLA', 'GOOGL', 'AMZN', 'NVDA', 'META', 'NFLX']

export const SENTIMENT_COLORS: Record<SentimentLabel, string> = {
  positive: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  neutral: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  negative: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
}

export const SENTIMENT_CHART_COLORS: Record<SentimentLabel, string> = {
  positive: '#10b981',
  neutral: '#f59e0b',
  negative: '#f43f5e',
}

export function normalizeLabel(label: string): SentimentLabel {
  const normalized = label.toLowerCase()
  if (normalized === 'positive' || normalized === 'negative' || normalized === 'neutral') {
    return normalized
  }
  return 'neutral'
}

export function getSentimentBadgeClass(label: string): string {
  return SENTIMENT_COLORS[normalizeLabel(label)]
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString()
}

export function toScoreWidth(score: number): number {
  const clamped = Math.max(-1, Math.min(1, score))
  return ((clamped + 1) / 2) * 100
}
