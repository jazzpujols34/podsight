# PodSight - Podcast AI Summarization Pipeline

## Development

**ALWAYS start servers with assigned ports:** Never use default ports (3000, 8000, 5173).

| Service                    | Port | URL                    |
|----------------------------|------|------------------------|
| Backend (pipeline control) | 3501 | http://localhost:3501  |
| Frontend (static site)     | 3500 | http://localhost:3500  |

```bash
# Backend - pipeline web UI (USE THIS)
./venv/bin/python src/server.py --port 3501

# Frontend - static site preview (optional)
cd public-site && python3 -m http.server 3500
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

- **Site:** Vercel (auto-deploy on push) - https://podsight.vercel.app
- **Pipeline:** GitHub Actions (10 AM + 7 PM Taiwan daily)
- **Telegram:** @podsight channel

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 auto_pipeline.py Flow                        │
├─────────────────────────────────────────────────────────────┤
│ For each podcast:                                            │
│   1. Parse RSS (01_parse_rss.py)                            │
│   2. Detect new episodes (RSS episodes - existing summaries)│
│   3. Download audio (02_download_audio.py)                  │
│   4. Transcribe (03_transcribe.py) - uses Groq Whisper      │
│   5. Summarize (04_summarize.py) - uses Gemini              │
│   6. Generate social drafts (05_generate_social.py)         │
│                                                              │
│ Then:                                                        │
│   7. Generate public site (generate_public_site.py)         │
│   8. Save pending Telegram episodes to JSON                 │
└─────────────────────────────────────────────────────────────┘
```

## GitHub Actions Workflow

The workflow is split to ensure Telegram notifications link to LIVE pages:

```
1. Run pipeline (process episodes, generate site)
2. Git commit/push → triggers Vercel deployment
3. Wait 3 minutes (Vercel build time)
4. Verify URL is live (from telegram.json)
5. Push to Telegram
6. Commit .telegram_published tracking
```

**Key files:**
- `.github/workflows/auto-pipeline.yml` - Main workflow
- `src/pipeline/auto_pipeline.py` - Pipeline orchestration
- `src/pipeline/push_telegram_batch.py` - Delayed Telegram push

## Data Structure

```
data/
├── gooaye/
│   ├── episodes.json          # RSS metadata
│   ├── audio/                 # .mp3 files (gitignored)
│   ├── transcripts/           # .txt files (tracked)
│   ├── summaries/             # _summary.txt files (tracked)
│   └── social_drafts/
│       ├── EP0640/
│       │   └── telegram.json  # Draft with message + URL
│       └── .telegram_published # Tracks pushed episodes
├── yutinghao/                 # Same structure, date-based IDs
├── zhaohua/                   # Same structure, EP#### IDs
└── .pending_telegram.json     # Temp file (gitignored)
```

## Episode ID Formats

| Podcast   | ID Format                    | URL Format                |
|-----------|------------------------------|---------------------------|
| gooaye    | `EP0640`                     | `/gooaye/0640/`           |
| zhaohua   | `EP1044`                     | `/zhaohua/1044/`          |
| yutinghao | `2026_1_12_一_標題...`       | `/yutinghao/2026-01-12/`  |

## Learned Rules

### Rule 1: New Episode Detection Must Compare RSS vs Summaries
- **Trigger:** GH Actions ran successfully but processed 0 episodes (1.5 min runs)
- **Root cause:** Detection counted audio files before/after download. But transcripts/summaries are in git, so GH Actions sees existing transcripts → skips everything.
- **Fix:** Compare RSS feed episodes against existing summaries, not audio file counts.
- **Date:** 2026-03-01

### Rule 2: Telegram Push Must Wait for Vercel Deployment
- **Trigger:** Users clicked Telegram link → 404 because Vercel hadn't deployed yet
- **Root cause:** Telegram push happened BEFORE git push (which triggers Vercel)
- **Fix:** Split into two phases: (1) pipeline + git push, (2) wait 3 min + verify URL + push TG
- **Date:** 2026-03-01

### Rule 3: Track Published Episodes to Prevent Duplicates
- **Trigger:** Same episode pushed to Telegram multiple times
- **Root cause:** `.telegram_published` file updated after TG push but not committed
- **Fix:** Add final git commit step after Telegram push to save tracking file
- **Date:** 2026-03-01

### Rule 4: Extract URLs from telegram.json, Don't Generate
- **Trigger:** URL verification failed for yutinghao (different ID format)
- **Root cause:** Code generated URLs assuming EP#### format, but yutinghao uses dates
- **Fix:** Extract URL from `href` in the telegram.json message itself
- **Date:** 2026-03-01

### Rule 5: Scripts Must Exit with Error Codes
- **Trigger:** Pipeline reported success but transcription actually failed (missing API key)
- **Root cause:** Script used `return` instead of `sys.exit(1)` on error
- **Fix:** Always use `sys.exit(1)` for errors so subprocess.run() sees non-zero exit code
- **Date:** 2026-03-01

### Rule 6: Pre-populate Telegram Tracking Files
- **Trigger:** GH Actions pushed 15 old episodes to Telegram (EP0630-0634, etc.)
- **Root cause:** `.telegram_published` only tracked recent pushes, so ALL old summaries appeared "unpublished"
- **Fix:** Pre-populate tracking files with ALL existing episode IDs before enabling automation
- **Date:** 2026-03-02

### Rule 7: yutinghao Uses Date Prefix for Episode Detection
- **Trigger:** yutinghao new episodes not detected ("No new episodes")
- **Root cause:** `get_episodes_from_rss()` only handled `episode_number`, yutinghao has None
- **Fix:** Extract date from title (`2026/3/2(一)...` → `2026_3_2_`) and match against summary filenames
- **Date:** 2026-03-02

### Rule 8: yutinghao Draft Folders Use Full Titles
- **Trigger:** "No Telegram draft for 2026_3_2_" error
- **Root cause:** Detection uses date prefix but draft folders have full title
- **Fix:** `find_draft_folder()` searches for folders starting with date prefix
- **Date:** 2026-03-02

### Rule 9: Normalize ID Formats When Reading Tracking Files
- **Trigger:** GH Actions pushed 5 old yutinghao episodes (0204, 0205, 0206, 0209, 0302)
- **Root cause:** `.telegram_published` had full folder names, but `get_summary_episodes()` returns date prefixes - they never matched
- **Fix:** `get_published_episodes()` extracts date prefix from full folder names for yutinghao
- **Date:** 2026-03-03

## Debugging Tips

```bash
# Check what episodes need processing
./venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
from pipeline.auto_pipeline import get_episodes_needing_summary, get_unpublished_episodes
for p in ['gooaye', 'yutinghao', 'zhaohua']:
    need = get_episodes_needing_summary(p)
    unpub = get_unpublished_episodes(p)
    print(f'{p}: {len(need)} need summary, {len(unpub)} unpublished')
"

# Test Telegram URL extraction
./venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
from pipeline.push_telegram_batch import get_episode_url_from_draft
print(get_episode_url_from_draft('gooaye', 'EP0640'))
"

# Check GH Actions run status
gh run list --limit 5
gh run view <run-id> --log
```

## Git Tracking Strategy

| Content | Tracked | Reason |
|---------|---------|--------|
| Transcripts | Yes | Text files, needed for GH Actions to detect existing |
| Summaries | Yes | Text files, needed for GH Actions to detect existing |
| Audio | No | Large binary files, re-downloaded as needed |
| Social drafts | Yes | Contains Telegram message templates |
| .telegram_published | Yes | Prevents duplicate TG pushes |
| .pending_telegram.json | No | Temp file, cleared after TG push |
