# Session Handover - PodSight Pipeline

**Date:** 2026-03-03
**File Path:** `/Users/jazz.lien/Desktop/jazz/0_GitHub/Repositories/17_ultimate_Claude/gooaye_pipeline/HANDOVER.md`

## Current Status

**Pipeline is WORKING** - GH Actions successfully detects and processes new episodes for all 3 podcasts.

### Recent Fixes Applied (This Session)

| Issue | Root Cause | Fix | Commit |
|-------|------------|-----|--------|
| GH Actions 37s failure | `from src.config` wrong import | Changed to `from config` | `be3450c` |
| yutinghao not detected | `get_episodes_from_rss()` only handled `episode_number` | Added date extraction from title | `435255b` |
| yutinghao TG push failed | Date prefix didn't match full folder name | Added `find_draft_folder()` with prefix search | `19e59fa` |
| 15 old episodes pushed | `.telegram_published` not pre-populated | Pre-populated with all 103 episodes | `2d6b835` |
| 5 old yutinghao re-pushed | ID format mismatch (full names vs date prefix) | `get_published_episodes()` now extracts date prefix | `64e9c6d` |

### Episodes Processed Today
- yutinghao 2026-03-03 → https://t.me/podsight/53
- zhaohua EP1046 → https://t.me/podsight/47

## Key Files Modified

1. **`src/pipeline/auto_pipeline.py`**
   - `get_episodes_from_rss()` - handles yutinghao date format
   - `get_summary_episodes()` - extracts date prefix for yutinghao
   - `get_published_episodes()` - normalizes ID format when reading tracking file

2. **`src/pipeline/push_telegram_batch.py`**
   - `find_draft_folder()` - searches by date prefix for yutinghao

3. **`.github/workflows/auto-pipeline.yml`**
   - Split workflow: process → git push → wait 3min → TG push → commit tracking

4. **`CLAUDE.md`** - Added 9 learned rules from debugging

## Known Issues / Warnings

1. **GH Actions transcription can timeout** - If transcription takes too long, it fails silently with `Transcribed: 0`. Episodes need to be processed locally when this happens.

2. **yutinghao ID complexity** - Three different formats in play:
   - Detection: `2026_3_3_` (date prefix)
   - Folders: `2026_3_3_二_黃金衝高 中東之亂...` (full title)
   - Tracking: Mixed (code now handles both)

## Next Actions

1. **Monitor next GH Actions run** (7 PM Taiwan = 11:00 UTC)
   - Should only push NEW episodes
   - Check logs if any issues

2. **If episodes fail to process in GH Actions**, run locally:
   ```bash
   GROQ_API_KEY=gsk_... GEMINI_API_KEY=AIza... ./venv/bin/python src/pipeline/auto_pipeline.py
   ```

3. **To manually push to Telegram after local processing:**
   ```bash
   TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ./venv/bin/python src/pipeline/push_telegram_batch.py
   ```

## Cron Schedule

| Time (Taiwan) | UTC | Podcasts |
|---------------|-----|----------|
| 10:00 AM | 02:00 | yutinghao (morning upload) |
| 7:00 PM | 11:00 | zhaohua (afternoon) + gooaye (Wed/Sat) |

## Quick Debug Commands

```bash
# Check what needs processing
./venv/bin/python -c "
import sys; sys.path.insert(0, 'src')
from pipeline.auto_pipeline import get_episodes_needing_summary, get_unpublished_episodes
for p in ['gooaye', 'yutinghao', 'zhaohua']:
    need = get_episodes_needing_summary(p)
    unpub = get_unpublished_episodes(p)
    print(f'{p}: {len(need)} need summary, {len(unpub)} unpublished')
"

# Check GH Actions
gh run list --limit 5
gh run view <run-id> --log | grep -E "Processing|Error|Pushed"
```

## Documentation

- Full learned rules: `CLAUDE.md` (9 rules documented)
- Pipeline architecture diagram in `CLAUDE.md`
