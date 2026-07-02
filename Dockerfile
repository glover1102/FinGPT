FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY trading_service/ ./trading_service/
COPY fingpt/ ./fingpt/

EXPOSE 8000

CMD ["uvicorn", "trading_service.main:app", "--host", "0.0.0.0", "--port", "8000"]

