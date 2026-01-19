"""
Configuration for Gooaye podcast transcription pipeline.
"""
from pathlib import Path

# RSS Feed URL
RSS_URL = "https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml"

# Directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
EPISODES_FILE = DATA_DIR / "episodes.json"

# Create directories
for d in [DATA_DIR, AUDIO_DIR, TRANSCRIPT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Whisper settings
WHISPER_MODEL = "base"  # Testing with base model first (faster), can upgrade to large-v3 later
WHISPER_LANGUAGE = "zh"  # Chinese
WHISPER_DEVICE = "cpu"  # "cuda" for GPU, "cpu" for CPU (mps not supported by ctranslate2)

# Download settings
DOWNLOAD_WORKERS = 4  # Parallel downloads
DOWNLOAD_RETRY = 3

# Episode filtering (set to None to process all)
EPISODE_START = 625  # Test with EP620-624
EPISODE_END = 626    # 5 episodes total

# Output format
TIMESTAMP_FORMAT = "[{minutes:02d}:{seconds:02d}]"  # Matches SpotScribe format
