#!/usr/bin/env python3
"""
Automated pipeline for PodSight.
Checks for new episodes, runs full pipeline, and pushes to Telegram.
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
            log(f"  Error in {script_name}: {result.stderr[:500]}")
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


def get_summary_episodes(podcast: str) -> set:
    """Get set of all episode IDs that have summaries."""
    summaries_dir = DATA_DIR / podcast / "summaries"
    if not summaries_dir.exists():
        return set()

    eps = set()
    for summary_file in summaries_dir.glob("*_summary.txt"):
        ep_id = summary_file.stem.replace("_summary", "")
        eps.add(ep_id)
    return eps


def push_telegram(podcast: str, episode_id: str) -> bool:
    """Push a single episode to Telegram."""
    draft_file = DATA_DIR / podcast / "social_drafts" / episode_id / "telegram.json"

    if not draft_file.exists():
        log(f"  No Telegram draft for {episode_id}")
        return False

    try:
        from social.publishers.telegram import TelegramPublisher

        with open(draft_file, "r", encoding="utf-8") as f:
            content = json.load(f)

        pub = TelegramPublisher()
        result = pub.publish(content)

        if result.success:
            log(f"  Pushed to Telegram: {episode_id}")
            return True
        else:
            log(f"  Telegram push failed: {episode_id}")
            return False
    except Exception as e:
        log(f"  Telegram error: {e}")
        return False


def process_podcast(podcast: str) -> dict:
    """Run full pipeline for a podcast. Returns stats."""
    log(f"Processing {podcast}...")

    stats = {
        "podcast": podcast,
        "new_episodes": 0,
        "transcribed": 0,
        "summarized": 0,
        "telegram_pushed": 0,
        "errors": []
    }

    # Step 1: Parse RSS (detect new episodes)
    log(f"  Step 1: Parsing RSS...")
    before_eps = get_episode_count(podcast, "audio")
    if not run_script("01_parse_rss.py", podcast):
        stats["errors"].append("RSS parse failed")

    # Step 2: Download audio
    log(f"  Step 2: Downloading audio...")
    if not run_script("02_download_audio.py", podcast):
        stats["errors"].append("Download failed")
    after_eps = get_episode_count(podcast, "audio")
    stats["new_episodes"] = after_eps - before_eps

    if stats["new_episodes"] == 0:
        log(f"  No new episodes for {podcast}")
        return stats

    log(f"  Found {stats['new_episodes']} new episode(s)")

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

    # Push to Telegram for newly summarized episodes
    if new_summaries:
        log(f"  Pushing {len(new_summaries)} new episode(s) to Telegram...")
        for ep_id in sorted(new_summaries)[-5:]:  # Limit to 5 most recent
            if push_telegram(podcast, ep_id):
                stats["telegram_pushed"] += 1

    return stats


def main():
    log("=" * 60)
    log("PodSight Auto Pipeline")
    log("=" * 60)

    all_stats = []
    total_new = 0

    # Process each podcast
    for podcast in PODCASTS:
        stats = process_podcast(podcast)
        all_stats.append(stats)
        total_new += stats["new_episodes"]

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

    # Print summary
    log("=" * 60)
    log("Summary")
    log("=" * 60)

    for stats in all_stats:
        log(f"{stats['podcast']}:")
        log(f"  New episodes: {stats['new_episodes']}")
        log(f"  Transcribed: {stats['transcribed']}")
        log(f"  Summarized: {stats['summarized']}")
        log(f"  Telegram pushed: {stats['telegram_pushed']}")
        if stats['errors']:
            log(f"  Errors: {', '.join(stats['errors'])}")

    log("=" * 60)
    log(f"Total new episodes: {total_new}")
    log("Pipeline complete!")

    return 0 if total_new >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
