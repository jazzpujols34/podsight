# Session Handover - PodSight Pipeline

**Date:** 2026-03-05
**Status:** Pipeline WORKING. Major cleanup + name/ticker accuracy fixes shipped.

## What We Did This Session

### Phase 1: Codebase Cleanup
- Deleted dead code: `04_transcribe_gcp.py`, `auto_check_new_episodes.py`, `docs/gcp/`
- Fixed `server.py` reference to deleted script → now uses `auto_pipeline.py`
- **Commit:** `abdc512`

### Phase 2: Code Deduplication
- Extracted `parse_episode_range()` and `get_episode_number_from_filename()` into `config.py` (were duplicated in 3-4 scripts)
- Removed unused legacy config exports (`RSS_URL`, `AUDIO_DIR`, etc.)
- Fixed `sys.exit(1)` consistency in `03_transcribe.py` OpenAI branch
- **Commit:** `01b62dc`

### Phase 3: CLAUDE.md Rewrite
- Complete folder structure diagram, conventions, GH Actions docs
- Added Rule 10: don't duplicate shared utilities
- **Commit:** `1eb3181`

### Phase 4: Name & Ticker Accuracy Audit (BIG ONE)

**Guest name audit (zhaohua):** 55% error rate across summaries.
Fixed 19 files:

| Guest | Wrong | Correct | Episodes |
|-------|-------|---------|----------|
| 黃豐凱 | 黃峰凱 | 黃豐凱 | 7 eps |
| 林信富 | 幸福哥/林幸福 | 林信富 | 3 eps (incl EP1048) |
| 陳唯泰 | 韋泰 | 陳唯泰 | 4 eps |
| 股魚 | 古魚 | 股魚 | 2 eps |
| + 紀緯明, 艾綸, 林漢偉 | | | 3 eps |

**Stock ticker audit:** 53 corrections across 24 files in all 3 podcasts.
Critical: AOI→AAOI, 華城 1513→1519, Grok→Groq, plus 12+ wrong TW company names.

**Commits:** `6bdbe54`, `33f6cb2`, `6d7519a`

### Prevention: Custom Prompts Updated

All 3 `custom_prompt.txt` files now have:
1. **Correction tables** — known guest names + stock names that Whisper gets wrong
2. **寧可省略不可瞎猜 rule** — if AI isn't sure about a name/ticker, omit it or use sector name ("CPO 族群"). Wrong info is worse than no info.
3. **Transcription artifact warning** — don't copy nonsense names from transcript

## What to Watch

### Immediate (next few days)
- **Monitor next GH Actions runs** — do the updated prompts actually prevent name errors?
- EP1048 was the last episode with old prompts. EP1049+ should use the new ones.
- If names are still wrong, the correction table in the prompt may need to be more aggressive, or we may need a post-processing step.

### Known Remaining Issues
1. **Hallucinated company names from transcription** — The "omit if unsure" rule should help, but Gemini might still pass through garbage names from Whisper transcripts. If this keeps happening, consider adding a post-processing validation step that checks company names against a known-good list.
2. **yutinghao ID complexity** — Three different formats still in play (date prefix, full title, tracking). Works but fragile.
3. **GH Actions transcription timeouts** — If Groq rate-limits, transcription silently produces 0 output. Monitor.

### Product Readiness
Jazz is preparing to reach out to podcasters. The summaries must be bulletproof — no wrong names, no fake companies. The custom prompt updates are the first defense. If errors persist, consider:
- A **post-summarization validation** script that checks names/tickers against a whitelist
- **Human review queue** — flag new summaries for quick review before TG push

## Key Files Changed

| File | What changed |
|------|-------------|
| `src/config.py` | Added `parse_episode_range()`, removed legacy exports |
| `src/pipeline/03_transcribe.py` | Fixed `sys.exit(1)`, removed duplicate util |
| `src/pipeline/04_summarize.py` | Removed duplicate utils, imports from config |
| `src/pipeline/05_generate_social.py` | Same dedup |
| `src/pipeline/search.py` | Same dedup |
| `src/server.py` | Fixed reference to deleted script |
| `data/*/custom_prompt.txt` | Added correction tables + omit-if-unsure rule |
| `data/zhaohua/summaries/EP1014-1048` | Fixed guest names |
| `data/*/summaries/*` | Fixed stock tickers (24 files) |
| `CLAUDE.md` | Full rewrite with folder structure + conventions |

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

# Verify a new summary has correct names
grep -n "峰凱\|幸福\|韋泰\|古魚\|文明\|漢維\|漢瑋" data/zhaohua/summaries/EP1049_summary.txt
# (should return nothing if prompts worked)
```

## Cron Schedule

| Time (Taiwan) | UTC | Podcasts |
|---------------|-----|----------|
| 10:00 AM | 02:00 | yutinghao (morning upload) |
| 7:00 PM | 11:00 | zhaohua (afternoon) + gooaye (Wed/Sat) |
