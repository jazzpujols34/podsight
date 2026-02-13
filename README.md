# PodSight 聲見

**聽見弦外之音，看見核心觀點**

Multi-podcast transcription and AI summarization pipeline with a beautiful web dashboard.

![PodSight Logo](ui/assets/PodSight-Logo.jpeg)

## 🎯 Features

- **Multi-podcast support** - Handle multiple podcasts with different formats (numbered episodes or date-based)
- **Automated transcription** - Whisper-powered speech-to-text
- **AI summarization** - Claude, OpenAI, or Gemini for intelligent summaries
- **Web dashboard** - Beautiful UI for browsing transcripts and summaries
- **Full-text search** - Search across all transcripts
- **Edit & copy** - Edit summaries inline, copy with or without markdown

## 📁 Project Structure

```
gooaye_pipeline/
├── config.py                   # Configuration & podcast settings
├── podcasts.yaml               # Podcast definitions
├── run_pipeline.py             # Run all pipeline steps
├── server.py                   # FastAPI server + API
├── requirements.txt            # Python dependencies
├── scripts/
│   ├── 01_parse_rss.py         # Step 1: Parse RSS feed → episode list
│   ├── 02_download_audio.py    # Step 2: Download MP3 files
│   ├── 03_transcribe.py        # Step 3: Whisper transcription
│   ├── 04_summarize.py         # Step 4: AI-powered summarization
│   ├── auto_check_new_episodes.py  # Auto-detect & process new episodes
│   ├── search.py               # Search tool for transcripts
│   └── cron_setup.md           # Cron/launchd scheduling guide
├── ui/
│   ├── index.html              # Web dashboard
│   ├── assets/                 # Logo and images
│   ├── css/                    # Stylesheets (future)
│   └── js/                     # JavaScript (future)
├── data/
│   └── {podcast_slug}/         # Per-podcast data
│       ├── episodes.json       # Episode metadata
│       ├── audio/              # Downloaded MP3 files
│       ├── transcripts/        # Output transcripts
│       └── summaries/          # AI-generated summaries
└── gcp/
    ├── Dockerfile              # For cloud deployment
    └── DEPLOYMENT.md           # GCP setup guide
```

## 🎙️ Supported Podcasts

| Slug | Name | Host | Format |
|------|------|------|--------|
| `gooaye` | 股癌 Gooaye | 謝孟恭 (MK) | EP0001 - EP0624+ |
| `yutinghao` | 游庭皓的財經皓角 | 游庭皓 | Date-based |
| `zhaohua` | 兆華與股惑仔 | 兆華 | EP1010+ |

Add new podcasts by editing `podcasts.yaml`.

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.10+
python --version

# FFmpeg (required for audio processing)
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### Installation

```bash
cd gooaye_pipeline

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run Pipeline

```bash
# Run for default podcast (gooaye)
python run_pipeline.py

# Run for specific podcast
python run_pipeline.py --podcast yutinghao
python run_pipeline.py --podcast zhaohua

# Run single step
python run_pipeline.py --step 1  # Parse RSS only
python run_pipeline.py --step 4 --podcast yutinghao  # Summarize only

# List available podcasts
python run_pipeline.py --list
```

### Run Individual Scripts

```bash
# Set podcast via environment variable
PODCAST=yutinghao python scripts/01_parse_rss.py
PODCAST=yutinghao python scripts/04_summarize.py --ep 1-10
```

## 🖥️ Web Dashboard

Launch the web UI to browse and manage podcasts:

```bash
# Start server (opens browser)
python server.py

# Custom port
python server.py --port 8080
```

The dashboard provides:
- Pipeline status overview
- Episode browser with transcript/summary viewer
- Full-text search
- Edit summaries inline
- Copy transcripts/summaries

## 🌐 API Endpoints

- `GET /` - Web dashboard
- `GET /podcasts` - List all podcasts
- `GET /stats` - Podcast statistics
- `GET /episodes` - List episodes
- `GET /episode/{ep_number}` - Get transcript + summary
- `GET /episode/file/{filename}` - Get by filename (date-based)
- `GET /latest` - Most recent episode
- `GET /search?q={query}` - Search transcripts
- `PUT /episode/{ep_number}/summary` - Update summary
- `POST /pipeline/run` - Execute pipeline

API docs: `http://localhost:8000/docs`

## ⚙️ Configuration

### AI Summarization

Set API key for summarization:

```bash
# Gemini (default)
export GEMINI_API_KEY=your_key_here

# Or Claude
export ANTHROPIC_API_KEY=your_key_here

# Or OpenAI
export OPENAI_API_KEY=your_key_here
```

Choose provider:

```bash
python scripts/04_summarize.py --provider gemini
python scripts/04_summarize.py --provider anthropic --model claude-sonnet-4-20250514
python scripts/04_summarize.py --provider openai --model gpt-4o
```

### Adding New Podcasts

Edit `podcasts.yaml`:

```yaml
podcasts:
  mypodcast:
    name: "My Podcast Name"
    host: "Host Name"
    rss_url: "https://example.com/feed.xml"
    episode_pattern: 'EP(\d+)'  # Optional: regex for episode numbers
    episode_start: 1  # Optional: filter episodes
```

## 📊 Resource Estimates

| Hardware | Time per Episode | Storage |
|----------|------------------|---------|
| RTX 3080 | ~2 min | Audio: ~50MB |
| M1/M2 Mac | ~4-5 min | Transcript: ~100KB |
| GCP T4 | ~1.5 min | Summary: ~2KB |

## 🔧 Troubleshooting

### "No module named 'whisper'"
```bash
pip install openai-whisper
# or faster:
pip install faster-whisper
```

### CUDA out of memory
Use smaller model in `config.py`:
```python
WHISPER_MODEL = "medium"  # or "small"
```

### Transcription quality
- Use `large-v3` for best Mandarin results
- Ensure FFmpeg is installed: `ffmpeg -version`

## 📄 License

Pipeline code is MIT licensed. Podcast content belongs to respective creators.
