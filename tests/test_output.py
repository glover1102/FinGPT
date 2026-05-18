import asyncio
import httpx
import json

async def fetch_test():
    async with httpx.AsyncClient() as client:
        # Precheck Fail Example
        res1 = await client.post("http://127.0.0.1:8000/api/v1/research/analyze", json={
            "ticker": "INVALID_TICKER_TOOLONG",
            "question": "Validation check",
            "model": "fingpt"
        })
        print("--- Precheck Fail ---")
        print(json.dumps(res1.json(), indent=2))
        
        # Risk Attached Example
        res2 = await client.post("http://127.0.0.1:8000/api/v1/research/analyze", json={
            "ticker": "MSFT",
            "question": "Valid run",
            "model": "fingpt"
        })
        print("\n--- Valid Risk Injection ---")
        out = res2.json()
        out["raw_context"] = "ommited for brevity"
        print(json.dumps(out, indent=2))

if __name__ == "__main__":
    asyncio.run(fetch_test())
