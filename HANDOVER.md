# Session Handover - 2026-02-16

## What Was Being Worked On

### Social Push Feature
A feature to automatically generate social media drafts from AI summaries and publish them to multiple platforms.

**Platforms supported:**
- Twitter/X (Hook + Replies thread format)
- Threads (single post)
- LINE Notify (bullet message)
- Instagram (text-on-image card using Pillow)

### Performance Optimizations
Quick wins identified from codebase analysis to improve pipeline efficiency.

---

## What's Done

### Social Push Feature (Complete)
- [x] `social/` module with formatters and publishers
- [x] Twitter formatter with Hook + Replies format (better engagement)
- [x] Markdown stripping (platforms don't render markdown)
- [x] Instagram card image generator (Pillow)
- [x] `scripts/05_generate_social.py` script
- [x] Server endpoints: CRUD for drafts, publish single/all
- [x] Social Push UI card with preview modal
- [x] Step 5 added to pipeline runner

### Performance Optimizations (Complete)
- [x] **P3**: Groq delay reduced 180s → 60s (env customizable)
- [x] **E4**: Truncation warning shows % removed
- [x] **R1**: Shared `get_episode_number_from_filename()` in config.py
- [x] **U1**: Real-time stat updates + "last updated" timestamp
- [x] **E1**: RSS retry logic with exponential backoff

---

## What's Still In Progress / Known Issues

### Social Push - Not Yet Tested with Real APIs
Publishers are implemented but NOT tested with real credentials:
- `LINE_NOTIFY_TOKEN` - Easy to get (free)
- `TWITTER_API_KEY/SECRET/ACCESS_TOKEN/SECRET` - Requires $100/mo Basic tier
- `META_ACCESS_TOKEN/THREADS_USER_ID/INSTAGRAM_USER_ID` - Free but complex setup

### Twitter Format Refinement
Current main tweet format:
```
🎙️ Gooaye 股癌 EP0636 重點整理

💡 本集亮點：
• 峇里島奢華旅遊與育兒觀點
• 應用材料 (AMAT) 財報分析
...
👇 詳細內容請看回覆
```
User wanted: "Gooaye 股癌 {EP_Title} 重點整理" - may need episode title from RSS.

### Remaining Optimizations (Not Done)
- **P1**: Parallel summarization (50% faster) - 2hrs effort
- **P4**: Search indexing for large corpus - 3hrs effort
- **U3**: Timestamp sync (click transcript → seek audio) - 2hrs effort
- **U5**: Bulk export actions - 2.5hrs effort

---

## Exact Next Steps

1. **Test Social Push in UI**
   - Visit http://127.0.0.1:3500
   - Check "Social Push" card shows EP0636 draft
   - Click "預覽" to verify content displays correctly

2. **Set Up LINE Notify (Quick Win)**
   ```bash
   # Get token from https://notify-bot.line.me/
   echo "LINE_NOTIFY_TOKEN=your_token" >> .env
   ```
   - Test publish to LINE from UI

3. **Decide on Twitter API**
   - $100/mo Basic tier required for posting
   - Alternative: Manual copy-paste from preview

4. **Generate More Social Drafts**
   ```bash
   PODCAST=gooaye ./venv/bin/python scripts/05_generate_social.py
   ```

---

## Blockers / Decisions Needed

1. **Twitter API Cost**: Is $100/mo worth it for auto-posting?
   - Alternative: Use preview modal for manual copy-paste

2. **Instagram Setup Complexity**: Requires Facebook Business account
   - Worth the effort? Or skip for now?

3. **Episode Title in Twitter**: RSS titles are just emojis (e.g., "EP636 | 🐚")
   - Use generic "EP636 重點整理" format? Or parse better title from summary?

---

## Server Status

- **Port**: 3500
- **Status**: Running
- **Branch**: `feature/podsight-branding`
- **Last commit**: `94744a9` - feat: add Social Push feature + performance optimizations

---

## Files Changed This Session

### New Files
- `social/` - Complete module (formatters + publishers)
- `scripts/05_generate_social.py` - Social draft generator

### Modified Files
- `config.py` - Added `get_episode_number_from_filename()`
- `server.py` - Added social endpoints, step 5
- `ui/index.html` - Social Push UI, real-time stats
- `scripts/01_parse_rss.py` - RSS retry logic
- `scripts/03_transcribe.py` - Reduced Groq delay
- `scripts/04_summarize.py` - Truncation warning

### Data (Not Committed)
- `data/gooaye/social_drafts/EP0636/` - Test draft with all platform content
