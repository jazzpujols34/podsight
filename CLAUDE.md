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
- `GROQ_API_KEY` - Whisper transcription (required)
- `GEMINI_API_KEY` - Summarization (required)
- `TELEGRAM_BOT_TOKEN` - Channel posting (required for TG push)
- `TELEGRAM_CHAT_ID` - Target channel (required for TG push)

## Podcasts

| ID        | Name                | Schedule        |
|-----------|---------------------|-----------------|
| gooaye    | 股癌                | Wed/Sat         |
| yutinghao | 游庭皓的財經皓角    | Daily ~9 AM     |
| zhaohua   | 兆華與股惑仔        | Daily afternoon |

## Deployment

- **Site:** Vercel (auto-deploy on push) - https://podsight.tw
- **Pipeline:** GitHub Actions (10 AM + 7 PM Taiwan daily)
- **Telegram:** @podsight channel

## Folder Structure

```
gooaye_pipeline/
├── src/
│   ├── config.py                  # Podcast configs, shared utils (parse_episode_range, etc.)
│   ├── server.py                  # FastAPI web UI backend (port 3501)
│   ├── pipeline/
│   │   ├── 01_parse_rss.py        # Step 1: Fetch RSS feed → episodes.json
│   │   ├── 02_download_audio.py   # Step 2: Download MP3s
│   │   ├── 03_transcribe.py       # Step 3: Audio → text (Groq Whisper)
│   │   ├── 04_summarize.py        # Step 4: Transcript → summary (Gemini)
│   │   ├── 05_generate_social.py  # Step 5: Summary → social drafts
│   │   ├── auto_pipeline.py       # Orchestrator: runs all steps for all podcasts
│   │   ├── generate_public_site.py # Static HTML site generator
│   │   ├── push_telegram_batch.py # Telegram push (runs after Vercel deploy)
│   │   └── search.py              # CLI search tool for transcripts/summaries
│   └── social/
│       ├── draft.py               # Draft storage model (SocialDraft, DraftManager)
│       ├── image_generator.py     # Instagram card image generation (Pillow)
│       ├── formatters/            # Platform-specific content formatters
│       │   ├── base.py            # SummaryContent parser + BaseFormatter ABC
│       │   ├── telegram.py        # Telegram HTML formatter (production)
│       │   ├── twitter.py         # Twitter thread formatter (UI only)
│       │   ├── threads.py         # Threads formatter (UI only)
│       │   ├── line.py            # LINE formatter (UI only)
│       │   └── instagram.py       # Instagram formatter (UI only)
│       └── publishers/            # Platform publish adapters
│           ├── base.py            # PublishResult base class
│           ├── telegram.py        # Telegram Bot API publisher (production)
│           └── twitter/threads/line/instagram.py  # Stubs (UI only)
├── ui/                            # Web UI frontend (served by server.py)
│   ├── index.html                 # Main SPA (pipeline control, draft mgmt)
│   ├── assets/                    # Logo images
│   └── manifest.json, sw.js       # PWA support
├── public-site/                   # Generated static site (deployed to Vercel)
├── data/                          # Episode data (per podcast)
│   ├── {podcast}/
│   │   ├── episodes.json          # RSS metadata
│   │   ├── custom_prompt.txt      # Optional: custom summarization prompt
│   │   ├── audio/                 # .mp3 files (gitignored)
│   │   ├── transcripts/           # .txt files (git tracked)
│   │   ├── summaries/             # _summary.txt files (git tracked)
│   │   └── social_drafts/
│   │       ├── {episode_id}/      # Per-episode draft folder
│   │       │   ├── draft.json     # Draft metadata
│   │       │   ├── telegram.json  # Telegram message + URL
│   │       │   └── *.json         # Other platform drafts
│   │       └── .telegram_published # Tracks published episodes
│   └── .pending_telegram.json     # Temp file for TG batch (gitignored)
├── main.py                        # CLI wrapper: `python main.py serve|pipeline`
├── podcasts.yaml                  # Podcast configuration (RSS URLs, patterns)
├── requirements.txt               # Python dependencies
└── .github/workflows/auto-pipeline.yml  # CI/CD schedule
```

## Pipeline Architecture

```
auto_pipeline.py (orchestrator)
├── For each podcast (gooaye, yutinghao, zhaohua):
│   ├── 01_parse_rss.py          → episodes.json
│   ├── Compare RSS vs summaries → detect new episodes
│   ├── 02_download_audio.py     → audio/*.mp3
│   ├── 03_transcribe.py         → transcripts/*.txt (Groq Whisper)
│   ├── 04_summarize.py          → summaries/*_summary.txt (Gemini)
│   └── 05_generate_social.py    → social_drafts/*/telegram.json
├── generate_public_site.py      → public-site/**/*.html
└── Save .pending_telegram.json  → queued for push after deploy
```

## GitHub Actions Workflow

Schedule: 02:00 UTC + 11:00 UTC (10 AM + 7 PM Taiwan)

The workflow is split into two phases to ensure Telegram links work:

```
Phase 1: Pipeline + Deploy
  1. Run auto_pipeline.py (process all podcasts)
  2. Git commit + push → triggers Vercel deployment

Phase 2: Telegram (after Vercel is live)
  3. Wait 3 minutes for Vercel build
  4. Verify URL from telegram.json is HTTP 200
  5. Run push_telegram_batch.py
  6. Git commit .telegram_published tracking
```

**Secrets required:** `GROQ_API_KEY`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

## Key Conventions

### Shared Utilities in config.py
- `get_podcast_config(slug)` — Get podcast config (env `PODCAST` override)
- `get_episode_number_from_filename(filename)` — Extract EP number from filenames
- `parse_episode_range(range_str)` — Parse "620" or "620-625" into tuple
- **Do NOT duplicate these** in individual scripts. Import from config.

### Episode ID Formats

| Podcast   | ID Format                    | URL Format                |
|-----------|------------------------------|---------------------------|
| gooaye    | `EP0640`                     | `/gooaye/0640/`           |
| zhaohua   | `EP1044`                     | `/zhaohua/1044/`          |
| yutinghao | `2026_1_12_一_標題...`       | `/yutinghao/2026-01-12/`  |

### Error Handling
- **All pipeline scripts must use `sys.exit(1)` on errors** — not `return`.
  `auto_pipeline.py` checks subprocess exit codes to decide whether to continue.
- Individual script failures stop the chain for that podcast only.
- The orchestrator always completes (exit 0) so downstream steps (commit, TG push) still run.

### Social Platforms
- **Telegram** is the only production-active publisher (auto-pushed via GH Actions).
- Twitter, Threads, LINE, Instagram formatters/publishers exist for the web UI but have no API credentials.

### Git Tracking

| Content | Tracked | Reason |
|---------|---------|--------|
| Transcripts | Yes | Needed for GH Actions to detect existing episodes |
| Summaries | Yes | Needed for GH Actions to detect existing episodes |
| Audio | No | Large binary files, re-downloaded as needed |
| Social drafts | Yes | Contains Telegram message templates |
| .telegram_published | Yes | Prevents duplicate TG pushes |
| .pending_telegram.json | No | Temp file, cleared after TG push |

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

## SEO Requirements

The public site needs these for Google discoverability (target: 台灣 podcast listeners):

### Technical SEO (auto-generated by `generate_public_site.py`)
- **sitemap.xml** — All episode URLs with lastmod dates. Submitted to Google Search Console.
- **robots.txt** — Points to sitemap, allows all crawling.
- **JSON-LD structured data** — `Article` + `PodcastEpisode` schema on every episode page.
- **SEO titles** — Format: `{podcast_name} {episode_id} 重點整理｜AI 摘要 — PodSight`
  - gooaye: `股癌 EP0643 重點整理｜AI 摘要 — PodSight`
  - yutinghao: `游庭皓 2026-03-11 重點整理｜AI 摘要 — PodSight` (uses host name, not show name)
  - zhaohua: `兆華 EP1053 重點整理｜AI 摘要 — PodSight`
- **Meta descriptions** — Uses episode TLDR (first 150 chars), not generic text.

### Domain
- **Current:** `podsight.tw` (low domain authority)
- **Target:** `podsight.tw` (ccTLD signals Taiwan geo-targeting to Google)
- When domain is set up, update `SITE_URL` in `generate_public_site.py`

### Our SEO Edge
- **Speed**: Summaries publish within hours of episode air (Vocus writers take days)
- **Consistency**: Every episode, every podcast, every time
- **Structure**: Stock mentions, key quotes, topics — all searchable

## Learned Rules

### Rule 1: New Episode Detection Must Compare RSS vs Summaries
- **Trigger:** GH Actions ran successfully but processed 0 episodes (1.5 min runs)
- **Root cause:** Detection counted audio files before/after download. But transcripts/summaries are in git, so GH Actions sees existing transcripts -> skips everything.
- **Fix:** Compare RSS feed episodes against existing summaries, not audio file counts.
- **Date:** 2026-03-01

### Rule 2: Telegram Push Must Wait for Vercel Deployment
- **Trigger:** Users clicked Telegram link -> 404 because Vercel hadn't deployed yet
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
- **Fix:** Extract date from title (`2026/3/2(一)...` -> `2026_3_2_`) and match against summary filenames
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

### Rule 10: Don't Duplicate Shared Utilities
- **Trigger:** `get_episode_number_from_filename()` and `parse_episode_range()` were copy-pasted in 3-4 scripts
- **Root cause:** Each script defined its own version instead of importing from config.py
- **Fix:** Centralize shared utilities in `src/config.py`. Import, don't duplicate.
- **Date:** 2026-03-04
