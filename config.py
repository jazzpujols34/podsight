"""
Configuration for podcast transcription pipeline.
Supports multiple podcasts via podcasts.yaml.
"""
import os
import re
from pathlib import Path
from typing import Optional

import yaml

# Base directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# Load podcasts config
PODCASTS_FILE = BASE_DIR / "podcasts.yaml"
with open(PODCASTS_FILE, 'r', encoding='utf-8') as f:
    _config = yaml.safe_load(f)

PODCASTS = _config['podcasts']
DEFAULT_PODCAST = _config['default']
WHISPER_CONFIG = _config['whisper']
DOWNLOAD_CONFIG = _config['download']


class PodcastConfig:
    """Configuration for a single podcast."""

    def __init__(self, slug: str):
        if slug not in PODCASTS:
            available = ', '.join(PODCASTS.keys())
            raise ValueError(f"Unknown podcast: {slug}. Available: {available}")

        self._data = PODCASTS[slug]
        self.slug = slug
        self.name = self._data['name']
        self.rss_url = self._data['rss_url']
        self.language = self._data.get('language', 'zh')
        self.episode_start = self._data.get('episode_start')
        self.episode_end = self._data.get('episode_end')
        self.episode_pattern = self._data.get('episode_pattern')
        self.max_episodes = self._data.get('max_episodes')  # Limit for daily podcasts

        # Podcast-specific data directories
        self.data_dir = DATA_DIR / slug
        self.audio_dir = self.data_dir / "audio"
        self.transcript_dir = self.data_dir / "transcripts"
        self.summary_dir = self.data_dir / "summaries"
        self.episodes_file = self.data_dir / "episodes.json"

        # Create directories
        for d in [self.data_dir, self.audio_dir, self.transcript_dir, self.summary_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def extract_episode_number(self, title: str) -> Optional[int]:
        """Extract episode number from title using podcast's pattern."""
        if not self.episode_pattern:
            return None
        match = re.search(self.episode_pattern, title, re.IGNORECASE)
        return int(match.group(1)) if match else None


def get_podcast_config(slug: Optional[str] = None) -> PodcastConfig:
    """Get podcast configuration by slug, or default if not specified."""
    # Check environment variable first (for subprocess calls)
    env_podcast = os.environ.get('PODCAST')
    slug = slug or env_podcast or DEFAULT_PODCAST
    return PodcastConfig(slug)


def list_podcasts() -> dict:
    """Return all available podcasts."""
    return {slug: p['name'] for slug, p in PODCASTS.items()}


# -------------------------------------------
# Legacy exports for backwards compatibility
# These use the default podcast (gooaye)
# -------------------------------------------
_default = get_podcast_config()

RSS_URL = _default.rss_url
AUDIO_DIR = _default.audio_dir
TRANSCRIPT_DIR = _default.transcript_dir
EPISODES_FILE = _default.episodes_file

# Whisper settings (from global config)
WHISPER_MODEL = WHISPER_CONFIG['model']
WHISPER_LANGUAGE = WHISPER_CONFIG.get('language', 'zh')
WHISPER_DEVICE = "cpu"  # mps not supported by ctranslate2
WHISPER_PROVIDER = WHISPER_CONFIG.get('provider', 'groq')

# Download settings
DOWNLOAD_WORKERS = DOWNLOAD_CONFIG.get('workers', 4)
DOWNLOAD_RETRY = DOWNLOAD_CONFIG.get('retry', 3)

# Episode filtering (for default podcast)
EPISODE_START = _default.episode_start
EPISODE_END = _default.episode_end

# Output format
TIMESTAMP_FORMAT = "[{minutes:02d}:{seconds:02d}]"
