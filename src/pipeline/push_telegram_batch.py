#!/usr/bin/env python3
"""
Push pending episodes to Telegram.
Runs AFTER Vercel deployment to ensure URLs are live.
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# Add src to path
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
PENDING_TG_FILE = DATA_DIR / ".pending_telegram.json"


def log(msg: str):
    """Print timestamped log message."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_episode_url_from_draft(podcast: str, episode_id: str) -> str | None:
    """Extract the frontend URL from the telegram draft file."""
    import re
    draft_file = DATA_DIR / podcast / "social_drafts" / episode_id / "telegram.json"
    if not draft_file.exists():
        return None

    with open(draft_file, "r", encoding="utf-8") as f:
        content = json.load(f)

    # Extract URL from href in message
    match = re.search(r'href="(https://[^"]+)"', content.get("message", ""))
    if match:
        return match.group(1)
    return None


def verify_url_live(url: str, max_retries: int = 5, retry_delay: int = 30) -> bool:
    """Check if a URL is live (returns 200). Retries on failure."""
    for attempt in range(max_retries):
        try:
            response = requests.head(url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                return True
            log(f"  URL check {attempt + 1}/{max_retries}: {url} returned {response.status_code}")
        except requests.RequestException as e:
            log(f"  URL check {attempt + 1}/{max_retries}: {url} failed - {e}")

        if attempt < max_retries - 1:
            log(f"  Retrying in {retry_delay}s...")
            time.sleep(retry_delay)

    return False


def get_published_episodes(podcast: str) -> set:
    """Get set of episode IDs already published to Telegram."""
    published_file = DATA_DIR / podcast / "social_drafts" / ".telegram_published"
    if not published_file.exists():
        return set()
    return set(published_file.read_text().strip().split("\n"))


def mark_published(podcast: str, episode_id: str):
    """Mark an episode as published to Telegram."""
    published_file = DATA_DIR / podcast / "social_drafts" / ".telegram_published"
    published_file.parent.mkdir(parents=True, exist_ok=True)
    with open(published_file, "a", encoding="utf-8") as f:
        f.write(f"{episode_id}\n")


def find_draft_folder(podcast: str, episode_id: str) -> Path | None:
    """Find the draft folder for an episode ID (handles date prefix matching)."""
    drafts_dir = DATA_DIR / podcast / "social_drafts"

    # Direct match first
    direct = drafts_dir / episode_id / "telegram.json"
    if direct.exists():
        return drafts_dir / episode_id

    # For yutinghao date prefixes (2026_3_2_), find folder starting with prefix
    if podcast == "yutinghao" and episode_id.endswith("_"):
        for folder in drafts_dir.iterdir():
            if folder.is_dir() and folder.name.startswith(episode_id):
                if (folder / "telegram.json").exists():
                    return folder

    return None


def push_telegram(podcast: str, episode_id: str) -> bool:
    """Push a single episode to Telegram."""
    # Check if already published
    if episode_id in get_published_episodes(podcast):
        log(f"  Skipping {episode_id} (already published)")
        return False

    draft_folder = find_draft_folder(podcast, episode_id)
    if not draft_folder:
        log(f"  No Telegram draft for {episode_id}")
        return False

    draft_file = draft_folder / "telegram.json"

    try:
        from social.publishers.telegram import TelegramPublisher

        with open(draft_file, "r", encoding="utf-8") as f:
            content = json.load(f)

        pub = TelegramPublisher()
        result = pub.publish(content)

        if result.success:
            mark_published(podcast, episode_id)
            log(f"  Pushed to Telegram: {episode_id} (URL: {result.url})")
            return True
        else:
            log(f"  Telegram push failed: {episode_id} - {result.error}")
            return False
    except Exception as e:
        log(f"  Telegram error: {e}")
        return False


def main():
    log("=" * 60)
    log("PodSight Telegram Batch Push")
    log("=" * 60)

    # Check required environment variables
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not os.environ.get("TELEGRAM_CHAT_ID"):
        log("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required")
        return 1

    # Load pending episodes
    if not PENDING_TG_FILE.exists():
        log("No pending episodes to push")
        return 0

    with open(PENDING_TG_FILE) as f:
        pending = json.load(f)

    if not pending:
        log("No pending episodes to push")
        PENDING_TG_FILE.unlink()
        return 0

    log(f"Found {len(pending)} episode(s) to push")

    # Verify first URL is live (confirms Vercel deployed)
    first_ep = pending[0]
    first_url = get_episode_url_from_draft(first_ep["podcast"], first_ep["episode_id"])

    if first_url:
        log(f"Verifying Vercel deployment: {first_url}")
        if not verify_url_live(first_url):
            log("ERROR: Frontend not deployed yet. Aborting Telegram push.")
            log("Episodes will be pushed on next pipeline run.")
            return 1
        log("Frontend is live!")
    else:
        log("WARNING: Could not extract URL from draft, skipping verification")

    log("Pushing to Telegram...")

    # Push all pending episodes
    pushed = 0
    for ep in pending:
        if push_telegram(ep["podcast"], ep["episode_id"]):
            pushed += 1

    # Clean up pending file
    PENDING_TG_FILE.unlink()

    log("=" * 60)
    log(f"Pushed {pushed}/{len(pending)} episodes to Telegram")
    log("Batch push complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
