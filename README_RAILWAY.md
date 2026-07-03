# Deploy FinGPT Sentiment API to Railway

## Quick Deploy

1. **Fork this repository**
2. **Create a Railway project**
   - Go to https://railway.app/
   - Click **New Project** → **Deploy from GitHub repo**
   - Select your fork
3. **Set environment variables** in Railway:

   ```bash
   FINNHUB_API_KEY=your_key_here
   FINGPT_MODEL_NAME=FinGPT/fingpt-sentiment_llama2-13b_lora
   BASE_MODEL_NAME=meta-llama/Llama-2-7b-chat-hf
   USE_8BIT=true
   HF_TOKEN=your_huggingface_token_if_required
   LOG_LEVEL=INFO
   ```

4. **Deploy** — Railway will redeploy automatically on push.

## API Endpoints

### Health Check

```bash
GET https://your-app.railway.app/health
```

### Analyze Custom Text

```bash
POST https://your-app.railway.app/analyze-sentiment
Content-Type: application/json

{
  "text": "Apple announces record Q3 earnings beating expectations",
  "ticker": "AAPL"
}
```

### Get Ticker Sentiment

```bash
GET https://your-app.railway.app/sentiment/AAPL?days_lookback=7&max_articles=20
```

### Batch Analysis

```bash
GET https://your-app.railway.app/batch-sentiment?tickers=AAPL,MSFT,NVDA&days_lookback=7
```

## Memory Requirements

- Minimum: 4GB RAM (8-bit loading preferred when available)
- Recommended: 8GB RAM
- Railway Pro is recommended for production traffic

## Local Testing

```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn trading_service.main:app --reload --port 8000
curl http://localhost:8000/health
curl -X POST http://localhost:8000/analyze-sentiment \
  -H "Content-Type: application/json" \
  -d '{"text":"Apple stock rises after strong earnings","ticker":"AAPL"}'
```

## Troubleshooting

- **Model loading is slow:** the first request downloads and loads the base model and LoRA weights.
- **Out of memory:** keep `USE_8BIT=true` and consider a larger Railway instance if CPU fallback is used.
- **No Finnhub data:** verify `FINNHUB_API_KEY`, then rely on the optional yfinance fallback if installed.

