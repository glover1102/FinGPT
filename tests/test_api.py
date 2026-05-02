import asyncio
import httpx
import time

async def fetch(ticker):
    try:
        async with httpx.AsyncClient() as client:
            start = time.time()
            data = {
                "ticker": ticker,
                "question": f"Analysis for {ticker}",
                "model": "fingpt",
                "top_k": 5
            }
            res = await client.post("http://127.0.0.1:8000/api/v1/research/analyze", json=data, timeout=300.0)
            print(f"[{ticker}] Status: {res.status_code}")
            try:
                print(f"[{ticker}] Body: {res.json()['status']} | Error: {res.json().get('error_metadata')}")
            except Exception:
                pass
            return res
    except Exception as e:
        print(f"[{ticker}] Client error: {e}")

async def main():
    print("Testing concurrency...")
    start = time.time()
    await asyncio.gather(
        fetch("MSFT"),
        fetch("AAPL"),
        fetch("GOOG")
    )
    print(f"Total time: {time.time() - start:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
