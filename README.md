# Gooaye 股癌 Podcast Transcription Pipeline

Automated pipeline to download and transcribe all 624+ episodes of the Gooaye (股癌) podcast by MK Hsieh (謝孟恭).

## 🎯 Goal

Create transcripts for building a "Mini MK" chatbot that thinks and responds like the podcast host.

## 📁 Project Structure

```
gooaye_pipeline/
├── config.py                   # Configuration settings
├── 01_parse_rss.py             # Step 1: Parse RSS feed → episode list
├── 02_download_audio.py        # Step 2: Download MP3 files
├── 03_transcribe.py            # Step 3: Whisper transcription
├── 04_summarize.py             # Step 4: AI-powered summarization
├── run_pipeline.py             # Run all steps
├── auto_check_new_episodes.py  # Auto-detect & process new episodes
├── search.py                   # Search tool for transcripts
├── server.py                   # FastAPI HTTP endpoint
├── cron_setup.md               # Cron/launchd scheduling guide
├── requirements.txt            # Python dependencies
├── data/
│   ├── episodes.json           # Episode metadata
│   ├── audio/                  # Downloaded MP3 files (EP0001.mp3, ...)
│   ├── transcripts/            # Output transcripts (EP0001.txt, ...)
│   ├── summaries/              # AI-generated summaries (EP0001_summary.txt)
│   └── notifications/          # New episode notifications
└── gcp/
    ├── Dockerfile              # For cloud deployment
    └── DEPLOYMENT.md           # GCP setup guide
```

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

# Windows
# Download from https://ffmpeg.org/download.html
```

### Installation

```bash
# Clone or download this folder
cd gooaye_pipeline

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run Pipeline

```bash
# Run everything (will take 20-50 hours depending on hardware)
python run_pipeline.py

# Or run steps individually:
python 01_parse_rss.py       # Get episode list (~30 seconds)
python 02_download_audio.py  # Download audio (~2-3 hours for 624 eps)
python 03_transcribe.py      # Transcribe (~20-40 hours)
python 04_summarize.py       # Generate AI summaries (requires API key)
```

### Process Specific Episodes

```bash
# Edit config.py to set episode range
EPISODE_START = 295  # Start from EP295
EPISODE_END = 624    # End at EP624

# Or use command line
python run_pipeline.py --from 295 --to 624
```

## 📝 Output Format

Transcripts match SpotScribe format for compatibility with your existing 4 episodes:

```
[00:00] 歡迎收聽股癌...
[07:25] 很快的又要過新的一年了所以這邊就先跟大家分享...
[07:42] 今年表現是大概就跟去年差不多他也覺得非常好...
```

Each episode generates:
- `EP0621.txt` - Human-readable transcript with timestamps
- `EP0621.json` - Machine-readable segments for RAG pipeline

## 🔍 Search Tool

Search through transcripts to find specific content:

```bash
# Basic search
python search.py "台積電"

# Search specific episode range
python search.py "台積電" --ep 620-630

# Search summaries only
python search.py "台積電" --summary

# Limit results
python search.py "台積電" --limit 50

# Output as JSON
python search.py "台積電" --json
```

## 🔄 Auto-Check New Episodes

Automatically detect and process new episodes:

```bash
# Check for new episodes and process them
python auto_check_new_episodes.py

# Dry run (check only, don't process)
python auto_check_new_episodes.py --dry-run

# With macOS desktop notification
python auto_check_new_episodes.py --notify
```

Set up automatic scheduling with cron/launchd - see `cron_setup.md` for details.

## 🌐 HTTP API Server

Start a FastAPI server to query transcripts via HTTP:

```bash
# Start server (default port 8000)
python server.py

# Custom port
python server.py --port 8080

# Development mode with auto-reload
python server.py --reload
```

**Endpoints:**
- `GET /episode/{ep_number}` - Get transcript + summary
- `GET /latest` - Get most recent episode
- `GET /search?q={query}` - Search transcripts
- `GET /episodes` - List all available episodes

API documentation available at `http://localhost:8000/docs`

## ⚙️ Configuration

Edit `config.py` to customize:

```python
# Whisper model (trade-off: accuracy vs speed)
WHISPER_MODEL = "large-v3"  # Best for Mandarin
# WHISPER_MODEL = "medium"  # Faster, slightly less accurate

# Device
WHISPER_DEVICE = "cuda"  # NVIDIA GPU
# WHISPER_DEVICE = "mps"  # Apple Silicon
# WHISPER_DEVICE = "cpu"  # No GPU (slowest)

# Parallel downloads
DOWNLOAD_WORKERS = 4
```

### AI Summarization

Step 4 requires an API key. Set environment variable:

```bash
# For Claude (default)
export ANTHROPIC_API_KEY=your_key_here

# For OpenAI
export OPENAI_API_KEY=your_key_here
```

Customize the provider and model:

```bash
python 04_summarize.py --provider openai --model gpt-4o
python 04_summarize.py --provider anthropic --model claude-sonnet-4-20250514
```

## ☁️ Cloud Deployment (GCP)

For faster processing, run on Google Cloud. See `gcp/DEPLOYMENT.md` for details.

**Recommended: Compute Engine with T4 GPU**
- Cost: ~$10-20
- Time: ~20 hours
- Commands:

```bash
# Create VM
gcloud compute instances create gooaye-transcribe \
    --zone=asia-east1-a \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --image-family=pytorch-latest-gpu \
    --image-project=deeplearning-platform-release \
    --boot-disk-size=100GB

# SSH and run
gcloud compute ssh gooaye-transcribe --zone=asia-east1-a
```

## 📊 Estimated Resources

| Hardware | Time per Episode | Total (624 eps) | Cost |
|----------|-----------------|-----------------|------|
| RTX 3080 | ~2 min | ~21 hours | $0 (local) |
| M1/M2 Mac | ~4-5 min | ~50 hours | $0 (local) |
| GCP T4 | ~1.5 min | ~16 hours | ~$10-20 |
| CPU only | ~15-20 min | ~200 hours | N/A |

**Storage:**
- Audio files: ~30-40 GB
- Transcripts: ~500 MB

## 🔧 Troubleshooting

### "No module named 'whisper'"
```bash
pip install openai-whisper
# or for faster version:
pip install faster-whisper
```

### CUDA out of memory
```python
# In config.py, use smaller model:
WHISPER_MODEL = "medium"  # or "small"
```

### Download failures
- Check your internet connection
- Some episodes might have moved - the script will log failures
- Re-run `02_download_audio.py` to retry failed downloads

### Transcription quality issues
- Whisper `large-v3` gives best Mandarin results
- If quality is poor, ensure audio downloaded correctly
- Check FFmpeg is installed: `ffmpeg -version`

## 📚 Next Steps: Building the Chatbot

After transcription, you'll have the corpus ready for:

1. **Segment labeling** - Classify sections (ad, 感想, 市場話題, etc.)
2. **Chunking** - Split into semantic chunks for RAG
3. **Embedding** - Generate embeddings with `text-embedding-3-large`
4. **Vector DB** - Store in Pinecone, Qdrant, or Chroma
5. **Persona prompt** - Craft MK's speaking style
6. **RAG chat** - Retrieve relevant context for each query

Let me know when you've completed transcription and we can build the next phase!

## 📄 License

This pipeline is for personal/educational use. Podcast content belongs to Gooaye/謝孟恭.
