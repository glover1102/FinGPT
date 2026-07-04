# FinGPT Sentiment Frontend

Modern React dashboard for the FinGPT Sentiment API.

## Stack

- React 18 + TypeScript + Vite
- Tailwind CSS
- Axios
- Recharts
- Lucide React

## Setup

```bash
npm install
cp .env.example .env
npm run dev
```

Set environment variables in `.env`:

```bash
VITE_API_BASE_URL=https://fingpt-production-c5b4.up.railway.app
```

## Build

```bash
npm run build
npm run preview
```

## Features

- Ticker search with autocomplete and debounced suggestions
- Sentiment summary card with gauge and confidence metrics
- News headline list (up to 5 headlines)
- Sentiment breakdown chart
- Batch ticker analysis and comparison grid
- Custom text analyzer with optional ticker context
- Dark mode with localStorage persistence
- API docs quick link (`/docs`)

## API Endpoints Used

- `GET /health`
- `GET /sentiment/{ticker}`
- `POST /analyze-sentiment`
- `GET /batch-sentiment?tickers=A,B,C`
- `GET /docs` (external link)

## Deployment

This app can be deployed as static assets.

- **Vercel** (recommended)
- **Netlify**
- **Railway**
- **GitHub Pages**

Use `npm run build` and deploy the generated `dist/` directory.
