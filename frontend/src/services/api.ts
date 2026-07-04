import axios from 'axios'
import type {
  AnalyzeSentimentRequest,
  HealthResponse,
  SentimentResponse,
  TickerSentimentResponse,
} from '../types'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'https://fingpt-production-c5b4.up.railway.app'

const api = axios.create({
  baseURL,
  timeout: 30000,
})

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health')
  return data
}

export async function getTickerSentiment(ticker: string): Promise<TickerSentimentResponse> {
  const { data } = await api.get<TickerSentimentResponse>(`/sentiment/${ticker.toUpperCase()}`)
  return data
}

export async function analyzeSentiment(payload: AnalyzeSentimentRequest): Promise<SentimentResponse> {
  const { data } = await api.post<SentimentResponse>('/analyze-sentiment', payload)
  return data
}

export async function getBatchSentiment(tickers: string[]): Promise<TickerSentimentResponse[]> {
  const params = new URLSearchParams({ tickers: tickers.join(',') })
  const { data } = await api.get<TickerSentimentResponse[]>(`/batch-sentiment?${params.toString()}`)
  return data
}

export default api
