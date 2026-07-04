import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { SENTIMENT_CHART_COLORS } from '../utils/helpers'

interface SentimentChartProps {
  score: number
}

export default function SentimentChart({ score }: SentimentChartProps) {
  const intensity = Math.round(Math.abs(score) * 100)
  const data = [
    {
      name: score >= 0.3 ? 'positive' : 'negative',
      value: intensity,
      color: score >= 0.3 ? SENTIMENT_CHART_COLORS.positive : SENTIMENT_CHART_COLORS.negative,
    },
    {
      name: 'neutral',
      value: score > -0.3 && score < 0.3 ? Math.max(40, 100 - intensity) : Math.max(15, 100 - intensity),
      color: SENTIMENT_CHART_COLORS.neutral,
    },
    {
      name: score < -0.3 ? 'negative' : 'positive',
      value: Math.max(0, 100 - intensity - (score > -0.3 && score < 0.3 ? Math.max(40, 100 - intensity) : Math.max(15, 100 - intensity))),
      color: score < -0.3 ? SENTIMENT_CHART_COLORS.negative : SENTIMENT_CHART_COLORS.positive,
    },
  ]

  return (
    <section className="panel">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Sentiment Breakdown</h2>
      <div className="mt-3 h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={60} outerRadius={90} paddingAngle={3}>
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              formatter={(value, name) => [`${Number(value ?? 0)}%`, String(name)]}
              contentStyle={{ borderRadius: 12, borderColor: '#334155' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
