# PodSight - Podcast AI Summarization Pipeline

## Development

**ALWAYS start servers with assigned ports:** Never use default ports (3000, 8000, 5173).

| Service         | Port |
|-----------------|------|
| Frontend (site) | 3500 |
| Backend (API)   | 3501 |

```bash
# Local preview
cd public-site && python3 -m http.server 3500

# API server (if needed)
./venv/bin/python src/server.py --port 3501
```

## Quick Commands

```bash
# Full pipeline (auto-detects new episodes)
./venv/bin/python src/pipeline/auto_pipeline.py

# Individual steps
PODCAST=yutinghao ./venv/bin/python src/pipeline/03_transcribe.py
PODCAST=yutinghao ./venv/bin/python src/pipeline/04_summarize.py
PODCAST=yutinghao ./venv/bin/python src/pipeline/05_generate_social.py

# Regenerate site
./venv/bin/python src/pipeline/generate_public_site.py
```

## Environment

API keys are loaded from `.env` via python-dotenv:
- `GROQ_API_KEY` - Whisper transcription
- `GEMINI_API_KEY` - Summarization
- `TELEGRAM_BOT_TOKEN` - Channel posting
- `TELEGRAM_CHAT_ID` - Target channel

## Podcasts

| ID        | Name                | Schedule        |
|-----------|---------------------|-----------------|
| gooaye    | 股癌                | Wed/Sat         |
| yutinghao | 游庭皓的財經皓角    | Daily ~9 AM     |
| zhaohua   | 兆華與股惑仔        | Daily afternoon |

## Deployment

- **Site:** Vercel (auto-deploy on push)
- **Pipeline:** GitHub Actions (10 AM + 7 PM Taiwan daily)
- **Telegram:** @podsight
