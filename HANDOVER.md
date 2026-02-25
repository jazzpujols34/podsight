# Session Handover - 2026-02-26

## Project: PodSight
AI-powered podcast summarization pipeline for 3 Taiwan finance podcasts.

**Repo:** https://github.com/jazzpujols34/podsight
**Live site:** https://podsight.vercel.app

## Current State

### Working Features
- Full pipeline: RSS → Download → Transcribe (Groq) → Summarize (Gemini) → Social drafts → Public site
- GitHub Actions automation (10am & 7pm Taiwan time)
- Telegram channel publishing (@podsight)
- Pagination (10 eps/page) on podcast listing pages
- Vercel auto-deploy on push

### Podcasts
| Podcast | Slug | Latest EP | Schedule |
|---------|------|-----------|----------|
| 股癌 Gooaye | gooaye | EP0639 | Wed & Sat |
| 游庭皓的財經皓角 | yutinghao | 2026-02-25 | Daily AM |
| 兆華與股惑仔 | zhaohua | EP1044 | Daily PM |

## Recent Changes (This Session)

1. **Pagination** - Added client-side pagination to podcast listing pages
2. **Episode sorting fix** - Fixed yutinghao date sorting (was alphabetical)
3. **Host names updated** - gooaye: 謝孟恭 Melody Hsieh, zhaohua: 李兆華
4. **GitHub Actions** - Added `auto-pipeline.yml` workflow
5. **Vercel fix** - Fixed webhook + git email issues, repo renamed to `podsight`
6. **URL fix** - Updated frontend URLs from `gooaye-agent.vercel.app` to `podsight.vercel.app`
7. **Data tracking** - Added summaries/transcripts to git (were gitignored, broke GitHub Actions)

## Key Files

```
src/pipeline/
├── auto_pipeline.py      # Full automation script
├── 01_parse_rss.py       # Fetch episodes from RSS
├── 02_download_audio.py  # Download MP3s
├── 03_transcribe.py      # Groq Whisper transcription
├── 04_summarize.py       # Gemini summarization
├── 05_generate_social.py # Social media drafts
└── generate_public_site.py # Static site generator

src/social/formatters/base.py  # Contains frontend URL (podsight.vercel.app)

.github/workflows/auto-pipeline.yml  # Scheduled automation

public-site/  # Vercel deploys this folder
```

## Environment Variables

Stored in `.env` locally and GitHub Secrets for Actions:
- `GROQ_API_KEY` - Whisper transcription
- `GEMINI_API_KEY` - AI summarization
- `TELEGRAM_BOT_TOKEN` - Bot for @podsight channel
- `TELEGRAM_CHAT_ID` - `-1003706212505`

## Known Issues / TODOs

1. **GitHub Actions transcription** - May fail with rate limits if many new episodes detected at once (Groq has 60s cooldown between calls)

2. **Regenerate drafts** - When URL or format changes, need to run:
   ```bash
   PODCAST=gooaye ./venv/bin/python src/pipeline/05_generate_social.py --regenerate
   ```

3. **Manual pipeline run:**
   ```bash
   GROQ_API_KEY=... GEMINI_API_KEY=... TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./venv/bin/python src/pipeline/auto_pipeline.py
   ```

## Git Info

- **Branch:** main
- **Remote:** origin → https://github.com/jazzpujols34/podsight.git
- **Latest commit:** `b4691d9` - fix: regenerate social drafts with correct URLs

## Quick Commands

```bash
# Run full pipeline
./venv/bin/python src/pipeline/auto_pipeline.py

# Regenerate public site only
./venv/bin/python src/pipeline/generate_public_site.py

# Local preview
cd public-site && python3 -m http.server 8080

# Push specific episode to Telegram
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
from social.publishers.telegram import TelegramPublisher
import json
with open('data/gooaye/social_drafts/EP0639/telegram.json') as f:
    content = json.load(f)
TelegramPublisher().publish(content)
"
```

## User Preferences

- Check new episodes twice daily (10am for YTH, 7pm for ZH/Gooaye)
- Full podcast names on UI (not abbreviations)
- Icons over emojis in UI
- Pagination with 10 episodes per page
