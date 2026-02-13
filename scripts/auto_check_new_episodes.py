#!/usr/bin/env python3
"""
Auto-detect new 股癌 episodes and process them through the pipeline.

This script is designed to be run via cron/launchd. It will:
1. Parse the RSS feed
2. Compare against existing episodes.json
3. If new episode(s) found:
   - Run the full pipeline (download -> transcribe -> summarize)
   - Save a notification to data/notifications/YYYY-MM-DD.txt
   - Print "NEW: EP{number} - {title}" to stdout
4. If no new episodes, print "No new episodes" and exit

Usage:
    python auto_check_new_episodes.py           # Check and process new episodes
    python auto_check_new_episodes.py --dry-run # Just check, don't process
    python auto_check_new_episodes.py --notify  # Also send desktop notification (macOS)

The script is idempotent and safe to run via cron.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    RSS_URL, DATA_DIR, EPISODES_FILE, AUDIO_DIR, TRANSCRIPT_DIR
)

# Directories
NOTIFICATION_DIR = DATA_DIR / "notifications"
SUMMARY_DIR = DATA_DIR / "summaries"
NOTIFICATION_DIR.mkdir(parents=True, exist_ok=True)


def load_existing_episodes() -> dict[int, dict]:
    """Load existing episodes from episodes.json."""
    if not EPISODES_FILE.exists():
        return {}

    with open(EPISODES_FILE, 'r', encoding='utf-8') as f:
        episodes = json.load(f)

    return {ep['episode_number']: ep for ep in episodes if ep.get('episode_number')}


def find_new_episodes(current: list[dict], existing: dict[int, dict]) -> list[dict]:
    """Find episodes that are in current but not in existing."""
    new_episodes = []

    for ep in current:
        ep_num = ep.get('episode_number')
        if ep_num and ep_num not in existing:
            new_episodes.append(ep)

    # Sort by episode number (ascending - process oldest first)
    new_episodes.sort(key=lambda x: x['episode_number'])
    return new_episodes


def run_pipeline_for_episode(ep_num: int) -> bool:
    """Run the full pipeline for a single episode."""
    script_dir = Path(__file__).parent

    # Step 1: RSS already parsed, just need to ensure episodes.json is up to date
    # Step 2: Download
    print(f"  Downloading EP{ep_num}...")
    result = subprocess.run(
        [sys.executable, str(script_dir / "02_download_audio.py")],
        env={**dict(__import__('os').environ),
             'EPISODE_FILTER': str(ep_num)},
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"  Download failed: {result.stderr}")
        return False

    audio_file = AUDIO_DIR / f"EP{ep_num:04d}.mp3"
    if not audio_file.exists():
        print(f"  Audio file not found after download")
        return False

    # Step 3: Transcribe
    print(f"  Transcribing EP{ep_num}...")
    result = subprocess.run(
        [sys.executable, str(script_dir / "03_transcribe.py")],
        env={**dict(__import__('os').environ),
             'EPISODE_FILTER': str(ep_num)},
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"  Transcription failed: {result.stderr}")
        return False

    transcript_file = TRANSCRIPT_DIR / f"EP{ep_num:04d}.txt"
    if not transcript_file.exists():
        print(f"  Transcript file not found after transcription")
        return False

    # Step 4: Summarize
    print(f"  Summarizing EP{ep_num}...")
    result = subprocess.run(
        [sys.executable, str(script_dir / "04_summarize.py"), "--ep", str(ep_num)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"  Summarization failed: {result.stderr}")
        # Don't fail the whole pipeline if summarization fails
        # (e.g., API key not set)

    return True


def save_notification(new_episodes: list[dict]) -> Path:
    """Save notification file with episode summaries."""
    today = datetime.now().strftime("%Y-%m-%d")
    notification_file = NOTIFICATION_DIR / f"{today}.txt"

    lines = [
        f"股癌新集數通知 - {today}",
        "=" * 40,
        "",
    ]

    for ep in new_episodes:
        ep_num = ep['episode_number']
        lines.append(f"NEW: EP{ep_num} - {ep['title']}")

        # Include summary if available
        summary_file = SUMMARY_DIR / f"EP{ep_num:04d}_summary.txt"
        if summary_file.exists():
            lines.append("")
            lines.append(summary_file.read_text(encoding='utf-8'))
        lines.append("")
        lines.append("-" * 40)
        lines.append("")

    notification_file.write_text("\n".join(lines), encoding='utf-8')
    return notification_file


def send_macos_notification(title: str, message: str):
    """Send a macOS desktop notification."""
    try:
        subprocess.run([
            'osascript', '-e',
            f'display notification "{message}" with title "{title}"'
        ], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # Silently fail if not on macOS or osascript fails


def main():
    parser = argparse.ArgumentParser(description="Check for new Gooaye episodes")
    parser.add_argument('--dry-run', action='store_true',
                        help="Check only, don't process or save")
    parser.add_argument('--notify', action='store_true',
                        help="Send desktop notification (macOS)")
    args = parser.parse_args()

    # Load existing episodes
    existing = load_existing_episodes()

    # Parse RSS feed for current episodes
    try:
        current = parse_rss_feed()
    except Exception as e:
        print(f"Error fetching RSS feed: {e}", file=sys.stderr)
        sys.exit(1)

    # Find new episodes
    new_episodes = find_new_episodes(current, existing)

    if not new_episodes:
        print("No new episodes")
        sys.exit(0)

    # Report new episodes
    print(f"Found {len(new_episodes)} new episode(s):")
    for ep in new_episodes:
        print(f"  NEW: EP{ep['episode_number']} - {ep['title']}")

    if args.dry_run:
        print("\nDry run - no processing performed")
        sys.exit(0)

    # Update episodes.json with new episodes
    all_episodes = list(existing.values()) + new_episodes
    all_episodes.sort(key=lambda x: x.get('episode_number', 0), reverse=True)
    with open(EPISODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_episodes, f, ensure_ascii=False, indent=2)
    print(f"\nUpdated {EPISODES_FILE}")

    # Process each new episode
    print("\nProcessing new episodes...")
    success_count = 0
    for ep in new_episodes:
        ep_num = ep['episode_number']
        print(f"\nProcessing EP{ep_num}: {ep['title'][:50]}...")

        if run_pipeline_for_episode(ep_num):
            success_count += 1
            print(f"  EP{ep_num} complete!")
        else:
            print(f"  EP{ep_num} failed!")

    # Save notification
    notification_file = save_notification(new_episodes)
    print(f"\nNotification saved to: {notification_file}")

    # Send desktop notification if requested
    if args.notify:
        titles = ", ".join(f"EP{ep['episode_number']}" for ep in new_episodes[:3])
        if len(new_episodes) > 3:
            titles += f" +{len(new_episodes) - 3} more"
        send_macos_notification("股癌新集數", titles)

    print(f"\nComplete: {success_count}/{len(new_episodes)} episodes processed successfully")


# RSS parsing logic (inline to avoid import issues)
import feedparser
import ssl
import re

ssl._create_default_https_context = ssl._create_unverified_context


def extract_episode_number(title: str) -> int | None:
    match = re.search(r'EP\.?(\d+)', title, re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_rss_feed() -> list[dict]:
    feed = feedparser.parse(RSS_URL)
    episodes = []
    for entry in feed.entries:
        audio_url = None
        for link in entry.get('links', []):
            if link.get('type', '').startswith('audio/'):
                audio_url = link.get('href')
                break
        for enc in entry.get('enclosures', []):
            if enc.get('type', '').startswith('audio/'):
                audio_url = audio_url or enc.get('href') or enc.get('url')
                break

        episode = {
            'title': entry.get('title', ''),
            'episode_number': extract_episode_number(entry.get('title', '')),
            'published': entry.get('published', ''),
            'audio_url': audio_url,
            'duration_str': entry.get('itunes_duration', ''),
            'guid': entry.get('id', ''),
            'summary': entry.get('summary', '')[:500] if entry.get('summary') else '',
        }
        episodes.append(episode)
    return episodes


if __name__ == "__main__":
    main()
