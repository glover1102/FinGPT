export type SentimentLabel = 'positive' | 'neutral' | 'negative'

export interface TickerSentimentResponse {
  ticker: string
  sentiment_score: number
  sentiment_label: SentimentLabel
  confidence: number
  news_count: number
  articles_analyzed: string[]
  timestamp: string
}

export interface SentimentResponse {
  sentiment_score: number
  sentiment_label: SentimentLabel
  confidence: number
  analyzed_text: string
  timestamp: string
}

export interface HealthResponse {
  status: string
  model_loaded: boolean
  finnhub_configured: boolean
}

export interface AnalyzeSentimentRequest {
  text: string
  ticker?: string
}
