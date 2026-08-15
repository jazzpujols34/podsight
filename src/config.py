"""
Configuration for podcast transcription pipeline.
Supports multiple podcasts via podcasts.yaml.
"""
import os
import re
from pathlib import Path
from typing import Optional

import yaml

# Base directories (project root is parent of src/)
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"

# Load podcasts config
PODCASTS_FILE = BASE_DIR / "podcasts.yaml"
try:
    with open(PODCASTS_FILE, 'r', encoding='utf-8') as f:
        _config = yaml.safe_load(f)
    if not _config:
        raise ValueError("Empty configuration file")
except FileNotFoundError:
    raise SystemExit(f"ERROR: Configuration file not found: {PODCASTS_FILE}")
except yaml.YAMLError as e:
    raise SystemExit(f"ERROR: Invalid YAML in {PODCASTS_FILE}: {e}")
except Exception as e:
    raise SystemExit(f"ERROR: Failed to load {PODCASTS_FILE}: {e}")

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
        self.host = self._data.get('host', self.name)  # Host name for summaries
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
        if not match:
            return None
        try:
            return int(match.group(1))
        except (ValueError, IndexError):
            return None


def get_podcast_config(slug: Optional[str] = None) -> PodcastConfig:
    """Get podcast configuration by slug, or default if not specified."""
    # Check environment variable first (for subprocess calls)
    env_podcast = os.environ.get('PODCAST')
    slug = slug or env_podcast or DEFAULT_PODCAST
    return PodcastConfig(slug)


def get_episode_number_from_filename(filename: str) -> Optional[int]:
    """Extract episode number from standard filename like EP0636.txt, EP0636_summary.txt.

    This is a utility function to avoid duplicating the regex pattern across scripts.
    For podcast-specific episode patterns, use PodcastConfig.extract_episode_number().
    """
    match = re.search(r'EP(\d+)', filename, re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_episode_range(range_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse episode range like '620-625' or '620'. Used by multiple scripts."""
    if '-' in range_str:
        parts = range_str.split('-')
        return int(parts[0]), int(parts[1])
    else:
        ep = int(range_str)
        return ep, ep


def list_podcasts() -> dict:
    """Return all available podcasts."""
    return {slug: p['name'] for slug, p in PODCASTS.items()}


# ---------------------------------------------------------------------------
# ASR term corrections
#
# Whisper systematically mis-hears domain jargon. Two layers fix it:
#   1. WHISPER_VOCAB_PROMPT biases decoding toward the right spellings.
#      Cheap, but Whisper only conditions on it loosely - treat it as a bonus.
#   2. TERM_CORRECTIONS rewrites whatever still comes out wrong. This is the
#      layer that actually guarantees the fix.
#
# Corrections run AFTER Traditional-Chinese conversion, so keys use Traditional
# forms. Only add a term when the wrong form has no legitimate meaning in this
# domain - a bad rule silently corrupts every future transcript.
# ---------------------------------------------------------------------------

WHISPER_VOCAB_PROMPT = (
    "以下是股癌 Podcast 的投資與半導體術語："
    "股癌、謝孟恭、主委、資料中心、功率半導體、被動元件、解禁、自結營收、滲透率、伏特數、"
    "800V HVDC、Power Rack、Power Center、Power Shelf、Sidecar、Busbar 銅排、Bus Duct、"
    "SSCB、BBU、UPS、SiC、GaN、IGBT、PSU、整流器、液冷、"
    "NVIDIA、AMD、Cerebras、Wafer-Scale Engine、Helios、"
    "Prefill、Decode、Disaggregated Inference、SRAM、HBM、KV cache、"
    "台積電、輝達、PE 乘數。"
)

# Latin-script terms: matched case-insensitively on word boundaries.
_LATIN_CORRECTIONS = {
    "Cerebrus": "Cerebras",
    "Celebras": "Cerebras",
    "Serebras": "Cerebras",
    "Desecrated Inference": "Disaggregated Inference",
    "Pre-File": "Prefill",
    "X-RAM": "SRAM",
    "Bus Doct": "Bus Duct",
    "TRUSST": "SST",   # Solid-State Transformer 固態變壓器 (confirmed 2026-08-16)
    "SHOFT": "Shelf",  # the 800V->54V power shelf (confirmed 2026-08-16)
    "let's but not least": "last but not least",
    "Roger Fedler": "Roger Federer",
}

# CJK terms: plain substring replacement, longest key first (see _CJK_ORDER).
_CJK_CORRECTIONS = {
    # Domain nouns Whisper reliably mangles
    "電壓中心": "資料中心",
    "電壓Center": "資料中心",
    "電壓 Center": "資料中心",
    "公立半導體": "功率半導體",
    "銅牌跟線纜": "銅排跟線纜",
    "福特數": "伏特數",
    "頭片": "投片",
    # Finance vocabulary
    "股票結晶": "股票解禁",
    "P1乘數": "PE 乘數",
    "字節的": "自結的",
    "完美討頂": "完美逃頂",
    # 原件 -> 元件: domain judgment. In a semiconductor/investing podcast this
    # is always 元件 (component), never 原件 (original document).
    "原件": "元件",
    # Show identity
    "谷愛": "股癌",
    "骨癌": "股癌",
    "孟公": "孟恭",
    # Recurring off-topic vocabulary (MK's training/travel segments)
    "握推": "臥推",
    # Bali: Whisper mis-hears it, and OpenCC mangles 里 -> 裡/裏 (see below).
    "八月島": "峇里島",
    "峇裡島": "峇里島",
    "峇裏島": "峇里島",
    "巴釐島": "峇里島",
    "巴厘島": "峇里島",
}

# Apply longer keys first so no short key eats a longer one's prefix.
_CJK_ORDER = sorted(_CJK_CORRECTIONS, key=len, reverse=True)

_LATIN_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(_LATIN_CORRECTIONS, key=len, reverse=True)),
    re.IGNORECASE,
)
_LATIN_LOOKUP = {k.lower(): v for k, v in _LATIN_CORRECTIONS.items()}

# Exposed for tests and for the backfill script.
TERM_CORRECTIONS = {**_LATIN_CORRECTIONS, **_CJK_CORRECTIONS}


def apply_term_corrections(text: str) -> str:
    """Fix Whisper's systematic domain-jargon errors.

    Run this AFTER convert_to_traditional() - the CJK keys are Traditional.
    """
    if not text:
        return text

    for wrong in _CJK_ORDER:
        text = text.replace(wrong, _CJK_CORRECTIONS[wrong])

    return _LATIN_PATTERN.sub(lambda m: _LATIN_LOOKUP[m.group(0).lower()], text)


# ---------------------------------------------------------------------------
# Simplified -> Traditional conversion
#
# Whisper returns a mix of Simplified and Traditional, sometimes within one
# episode. Converting blindly corrupts text that is ALREADY Traditional:
# Simplified merged 里/裡/裏 into 里, so every OpenCC s2* config rewrites
# 峇里島 -> 峇裡島. That also made conversion non-idempotent.
#
# So convert only text carrying zero Traditional-only characters. Mixed lines
# are left alone - under-converting is recoverable, corrupting is not. The
# handful of place names this leaves behind are handled in TERM_CORRECTIONS.
# ---------------------------------------------------------------------------

_OPENCC_CACHE: dict = {}


def _opencc(config: str):
    """Return a cached OpenCC converter. Raises ImportError if unavailable."""
    if config not in _OPENCC_CACHE:
        from opencc import OpenCC
        _OPENCC_CACHE[config] = OpenCC(config)
    return _OPENCC_CACHE[config]


def looks_simplified(text: str) -> bool:
    """True only when text is Simplified with no Traditional-only characters."""
    if not text:
        return False
    return _opencc('t2s').convert(text) == text and _opencc('s2t').convert(text) != text


def convert_to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Traditional (Taiwan). Idempotent.

    Raises ImportError if opencc is missing - callers decide how loud to be.
    """
    if not looks_simplified(text):
        return text
    return _opencc('s2twp').convert(text)


def normalize_transcript_text(text: str) -> str:
    """Full transcript cleanup: Traditional Chinese, then ASR term fixes."""
    return apply_term_corrections(convert_to_traditional(text))


# Whisper settings (from global config, env var overrides)
WHISPER_MODEL = WHISPER_CONFIG['model']
WHISPER_LANGUAGE = WHISPER_CONFIG.get('language', 'zh')
WHISPER_DEVICE = "cpu"  # mps not supported by ctranslate2
WHISPER_PROVIDER = os.environ.get('WHISPER_PROVIDER') or WHISPER_CONFIG.get('provider', 'groq')

# Download settings
DOWNLOAD_WORKERS = DOWNLOAD_CONFIG.get('workers', 4)
DOWNLOAD_RETRY = DOWNLOAD_CONFIG.get('retry', 3)

# Output format
TIMESTAMP_FORMAT = "[{minutes:02d}:{seconds:02d}]"
