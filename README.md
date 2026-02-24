# PodSight 聲見

**聽見弦外之音，看見核心觀點**

Multi-podcast transcription and AI summarization pipeline with a beautiful web dashboard.

**Live Site:** https://gooaye-agent.vercel.app/

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
├── main.py                     # Entry point (server & pipeline)
├── podcasts.yaml               # Podcast definitions
├── requirements.txt            # Python dependencies
├── src/
│   ├── config.py               # Configuration & podcast settings
│   ├── server.py               # FastAPI server + API
│   ├── pipeline/               # Pipeline scripts
│   │   ├── 01_parse_rss.py     # Parse RSS feed → episode list
│   │   ├── 02_download_audio.py # Download MP3 files
│   │   ├── 03_transcribe.py    # Whisper transcription
│   │   ├── 04_summarize.py     # AI summarization
│   │   └── ...
│   └── social/                 # Social media publishing
│       ├── formatters/         # Platform formatters
│       └── publishers/         # Platform publishers
├── ui/                         # Web dashboard
├── data/                       # Per-podcast data
│   └── {podcast_slug}/
│       ├── episodes.json       # Episode metadata
│       ├── transcripts/        # Output transcripts
│       └── summaries/          # AI-generated summaries
├── public-site/                # Static public site
└── docs/                       # Documentation
```

## 🎙️ Supported Podcasts

| Slug | Name | Host | Episodes |
|------|------|------|----------|
| `gooaye` | 股癌 Gooaye | 謝孟恭 (MK) | EP615 - EP638 (24 eps) |
| `yutinghao` | 游庭皓的財經皓角 | 游庭皓 | Date-based (34 eps) |
| `zhaohua` | 兆華與股惑仔 | 兆華 | 32 eps |

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
python main.py pipeline

# Run for specific podcast
python main.py pipeline -p yutinghao
python main.py pipeline -p zhaohua

# Run single step
python main.py pipeline --step 1  # Parse RSS only
python main.py pipeline --step 4 -p yutinghao  # Summarize only

# List available podcasts
python main.py pipeline --list
```

### Run Individual Scripts

```bash
# Set podcast via environment variable
PODCAST=yutinghao python src/pipeline/01_parse_rss.py
PODCAST=yutinghao python src/pipeline/04_summarize.py --ep 1-10
```

## 🖥️ Web Dashboard

Launch the web UI to browse and manage podcasts:

```bash
# Start server (opens browser)
python main.py

# Or explicitly
python main.py serve

# Custom port
python main.py serve --port 8080
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
python src/pipeline/04_summarize.py --provider gemini
python src/pipeline/04_summarize.py --provider anthropic --model claude-sonnet-4-20250514
python src/pipeline/04_summarize.py --provider openai --model gpt-4o
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
Use smaller model in `podcasts.yaml`:
```yaml
whisper:
  model: "medium"  # or "small"
```

### Transcription quality
- Use `large-v3` for best Mandarin results
- Ensure FFmpeg is installed: `ffmpeg -version`

## 📄 License

Pipeline code is MIT licensed. Podcast content belongs to respective creators.
