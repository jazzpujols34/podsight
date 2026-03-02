#!/usr/bin/env python3
"""
Automated pipeline for PodSight.
Checks for new episodes, runs full pipeline.
Telegram push is handled separately by push_telegram_batch.py (after Vercel deploys).
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Add src to path
BASE_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BASE_DIR / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
PODCASTS = ["gooaye", "yutinghao", "zhaohua"]

# Required environment variables
REQUIRED_ENV = ["GROQ_API_KEY", "GEMINI_API_KEY"]

# File to store episodes pending Telegram push
PENDING_TG_FILE = DATA_DIR / ".pending_telegram.json"


def log(msg: str):
    """Print timestamped log message."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_script(script_name: str, podcast: str, env_vars: dict = None) -> bool:
    """Run a pipeline script for a specific podcast."""
    script_path = BASE_DIR / "src" / "pipeline" / script_name

    env = os.environ.copy()
    env["PODCAST"] = podcast
    if env_vars:
        env.update(env_vars)

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            env=env,
            capture_output=True,
            text=True,
            timeout=600  # 10 min timeout
        )
        if result.returncode != 0:
            log(f"  Error in {script_name} (exit code {result.returncode}):")
            if result.stderr:
                log(f"    stderr: {result.stderr[:500]}")
            if result.stdout:
                log(f"    stdout: {result.stdout[-500:]}")  # Last 500 chars
            return False
        return True
    except subprocess.TimeoutExpired:
        log(f"  Timeout in {script_name}")
        return False
    except Exception as e:
        log(f"  Exception in {script_name}: {e}")
        return False


def get_episode_count(podcast: str, folder: str) -> int:
    """Count files in a data folder."""
    path = DATA_DIR / podcast / folder
    if not path.exists():
        return 0
    return len(list(path.glob("*")))


def get_unpublished_episodes(podcast: str) -> list:
    """Get list of episodes that have summaries but not published to Telegram."""
    summaries = get_summary_episodes(podcast)
    published = get_published_episodes(podcast)
    unpublished = summaries - published
    return sorted(list(unpublished))


def get_episodes_from_rss(podcast: str) -> set:
    """Get episode IDs from RSS feed (episodes.json)."""
    import re

    episodes_file = DATA_DIR / podcast / "episodes.json"
    if not episodes_file.exists():
        return set()

    with open(episodes_file) as f:
        episodes = json.load(f)

    eps = set()
    for ep in episodes:
        ep_num = ep.get("episode_number")
        title = ep.get("title", "")

        if ep_num:
            # gooaye, zhaohua: use episode number
            eps.add(f"EP{ep_num:04d}")
        elif podcast == "yutinghao" and title:
            # yutinghao: extract date from title like "2026/3/2(一)中東大戰..."
            match = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", title)
            if match:
                year, month, day = match.groups()
                # Format to match summary filename prefix: 2026_3_2_
                eps.add(f"{year}_{month}_{day}_")
    return eps


def get_episodes_needing_summary(podcast: str) -> set:
    """Get episodes that are in RSS but don't have summaries."""
    from config import get_podcast_config
    config = get_podcast_config(podcast)

    rss_eps = get_episodes_from_rss(podcast)
    summaries = get_summary_episodes(podcast)

    # Filter by episode_start if set
    if config.episode_start:
        rss_eps = {ep for ep in rss_eps if int(ep.replace("EP", "")) >= config.episode_start}

    return rss_eps - summaries


def get_summary_episodes(podcast: str) -> set:
    """Get set of all episode IDs that have summaries."""
    import re

    summaries_dir = DATA_DIR / podcast / "summaries"
    if not summaries_dir.exists():
        return set()

    eps = set()
    for summary_file in summaries_dir.glob("*_summary.txt"):
        filename = summary_file.stem.replace("_summary", "")

        if podcast == "yutinghao":
            # Extract date prefix: 2026_3_2_一_... -> 2026_3_2_
            match = re.match(r"(\d{4}_\d{1,2}_\d{1,2}_)", filename)
            if match:
                eps.add(match.group(1))
            else:
                # Non-date format (like _市場觀察_) - use full name
                eps.add(filename)
        else:
            # gooaye, zhaohua: EP0640
            eps.add(filename)
    return eps


def get_published_episodes(podcast: str) -> set:
    """Get set of episode IDs already published to Telegram."""
    published_file = DATA_DIR / podcast / "social_drafts" / ".telegram_published"
    if not published_file.exists():
        return set()
    return set(published_file.read_text().strip().split("\n"))


def save_pending_telegram(pending: list):
    """Save episodes pending Telegram push to a file."""
    with open(PENDING_TG_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2)
    log(f"Saved {len(pending)} episode(s) pending Telegram push")


def process_podcast(podcast: str) -> dict:
    """Run full pipeline for a podcast. Returns stats including pending TG episodes."""
    log(f"Processing {podcast}...")

    stats = {
        "podcast": podcast,
        "new_episodes": 0,
        "transcribed": 0,
        "summarized": 0,
        "pending_telegram": [],  # Episodes to push after Vercel deploys
        "errors": []
    }

    # Step 1: Parse RSS (detect new episodes)
    log(f"  Step 1: Parsing RSS...")
    if not run_script("01_parse_rss.py", podcast):
        stats["errors"].append("RSS parse failed")

    # Check for episodes needing processing (in RSS but no summary)
    need_processing = get_episodes_needing_summary(podcast)
    if not need_processing:
        log(f"  No new episodes for {podcast}")
        # Still check for unpublished episodes
        unpublished = get_unpublished_episodes(podcast)
        if unpublished:
            log(f"  Found {len(unpublished)} unpublished episode(s)")
            # Add to pending list (will be pushed after Vercel deploys)
            for ep_id in sorted(unpublished)[-5:]:
                stats["pending_telegram"].append({"podcast": podcast, "episode_id": ep_id})
        return stats

    stats["new_episodes"] = len(need_processing)
    log(f"  Found {stats['new_episodes']} episode(s) needing processing: {sorted(need_processing)[-3:]}")

    # Step 2: Download audio for episodes that need it
    log(f"  Step 2: Downloading audio...")
    if not run_script("02_download_audio.py", podcast):
        stats["errors"].append("Download failed")

    # Step 3: Transcribe
    log(f"  Step 3: Transcribing...")
    before_trans = get_episode_count(podcast, "transcripts")
    if not run_script("03_transcribe.py", podcast):
        stats["errors"].append("Transcription failed")
    after_trans = get_episode_count(podcast, "transcripts")
    stats["transcribed"] = after_trans - before_trans

    # Step 4: Summarize
    log(f"  Step 4: Summarizing...")
    before_summaries = get_summary_episodes(podcast)
    if not run_script("04_summarize.py", podcast):
        stats["errors"].append("Summarization failed")
    after_summaries = get_summary_episodes(podcast)
    new_summaries = after_summaries - before_summaries
    stats["summarized"] = len(new_summaries)

    # Step 5: Generate social drafts
    log(f"  Step 5: Generating social drafts...")
    if not run_script("05_generate_social.py", podcast):
        stats["errors"].append("Social draft generation failed")

    # Collect episodes for Telegram (will be pushed after Vercel deploys)
    if new_summaries:
        log(f"  Queuing {len(new_summaries)} episode(s) for Telegram...")
        for ep_id in sorted(new_summaries)[-5:]:  # Limit to 5 most recent
            stats["pending_telegram"].append({"podcast": podcast, "episode_id": ep_id})
    else:
        # Check for any unpublished episodes
        unpublished = get_unpublished_episodes(podcast)
        if unpublished:
            log(f"  Found {len(unpublished)} unpublished episode(s)")
            for ep_id in sorted(unpublished)[-5:]:
                stats["pending_telegram"].append({"podcast": podcast, "episode_id": ep_id})

    return stats


def main():
    log("=" * 60)
    log("PodSight Auto Pipeline")
    log("=" * 60)

    # Check required environment variables
    missing = [var for var in REQUIRED_ENV if not os.environ.get(var)]
    if missing:
        log(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        log("Please set these in your .env file or GitHub Actions secrets")
        return 1

    all_stats = []
    total_new = 0
    all_pending_tg = []

    # Process each podcast
    for podcast in PODCASTS:
        stats = process_podcast(podcast)
        all_stats.append(stats)
        total_new += stats["new_episodes"]
        all_pending_tg.extend(stats["pending_telegram"])

    # Generate public site if there were any new episodes
    if total_new > 0:
        log("Generating public site...")
        try:
            subprocess.run(
                [sys.executable, str(BASE_DIR / "src" / "pipeline" / "generate_public_site.py")],
                check=True,
                capture_output=True,
                text=True
            )
            log("Public site generated successfully")
        except subprocess.CalledProcessError as e:
            log(f"Public site generation failed: {e.stderr[:500]}")

    # Save pending Telegram episodes to file (will be pushed after Vercel deploys)
    if all_pending_tg:
        save_pending_telegram(all_pending_tg)
    else:
        # Clear any stale pending file
        if PENDING_TG_FILE.exists():
            PENDING_TG_FILE.unlink()

    # Print summary
    log("=" * 60)
    log("Summary")
    log("=" * 60)

    for stats in all_stats:
        log(f"{stats['podcast']}:")
        log(f"  New episodes: {stats['new_episodes']}")
        log(f"  Transcribed: {stats['transcribed']}")
        log(f"  Summarized: {stats['summarized']}")
        log(f"  Pending Telegram: {len(stats['pending_telegram'])}")
        if stats['errors']:
            log(f"  Errors: {', '.join(stats['errors'])}")

    log("=" * 60)
    log(f"Total new episodes: {total_new}")
    log(f"Total pending Telegram: {len(all_pending_tg)}")
    log("Pipeline complete! (Telegram push will run after Vercel deploy)")

    return 0 if total_new >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
