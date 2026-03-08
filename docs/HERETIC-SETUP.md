# gpt-oss-20b-heretic Setup (Local)

## 1) Download model from HF (already running)
```bash
hf download p-e-w/gpt-oss-20b-heretic \
  --local-dir /Users/ravenx/Models/hf/gpt-oss-20b-heretic
```

## 2) Start worker
```bash
cd ~/Projects/star-platinum-cluster
SPC_HERETIC_MODEL_DIR=/Users/ravenx/Models/hf/gpt-oss-20b-heretic \
python3 services/heretic_worker/main.py
```

## 3) Health check
```bash
curl -s http://127.0.0.1:9094/health | jq
```

## 4) Test generation
```bash
curl -s http://127.0.0.1:9094/run \
  -H 'content-type: application/json' \
  -d '{"prompt":"You are Dark Flame. One-line systems status."}' | jq
```

## Notes
- This repo model is safetensors (not GGUF), so run via `transformers` path.
- Keep Qwen 32b as scheduler local default unless SOUL-mode explicitly sets Heretic path.
