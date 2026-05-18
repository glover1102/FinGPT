# quant_stack

Minimal OpenBB + Qdrant + FinGPT inference pipeline with explicit WSL preflight checks.

## Runtime target

- WSL Ubuntu
- Python 3.12
- One active virtualenv

Windows Python is intentionally unsupported for this pipeline.

## Install

```bash
cd /mnt/f/LLM/FinGPT
. venv/bin/activate
pip install -r quant_stack/requirements-quant-stack.txt -c quant_stack/constraints-quant-stack.txt
```

If your virtualenv lives elsewhere, activate that environment first.

## Configure

```bash
cd /mnt/f/LLM/FinGPT/quant_stack
cp .env.example .env
```

Set `FMP_API_KEY` if you want transcript collection.
Set `HF_TOKEN` and ensure you have access to `meta-llama/Llama-2-7b-hf` if you want model inference.

## Preflight

```bash
cd /mnt/f/LLM/FinGPT/quant_stack
python doctor.py --check openbb
python doctor.py --check qdrant
python doctor.py --check model
python doctor.py --check all
```

## Run order

```bash
cd /mnt/f/LLM/FinGPT/quant_stack
python collect_openbb.py
python ingest_qdrant.py
python search_qdrant.py
python run_fingpt.py
```

## Common recovery commands

Start local Qdrant:

```bash
docker run -d --name qdrant -p 6333:6333 qdrant/qdrant:latest
```

Reinstall the pinned stack:

```bash
cd /mnt/f/LLM/FinGPT
. venv/bin/activate
pip install -r quant_stack/requirements-quant-stack.txt -c quant_stack/constraints-quant-stack.txt
```
