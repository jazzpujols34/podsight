#!/usr/bin/env python3
"""
Step 6 (optional): Index episodes with TypeSafe Jev for company/topic/view search tags.

For each episode in data/{podcast}/transcripts/*.json that also has a summary
but no index file yet (or every episode in --episodes with --force), asks Jev
three questions per ~60s window (company / topic / view) and writes
data/{podcast}/index/{episode_id}.json. See src/pipeline/jev_index.py.

This step is OPTIONAL and must never break the pipeline chain (Rule 11's
"loud but non-fatal" pattern):
  - Missing TYPESAFE_API_KEY -> loud WARNING to stderr, exit 0 (skip entirely).
  - One episode's Jev calls fail -> WARNING for that episode, skip it,
    continue with the rest, still exit 0.
  - A programming error (bad arguments, unreadable transcript JSON) exits 1.

Usage:
    PODCAST=gooaye python 06_index_jev.py                  # index everything missing an index
    PODCAST=gooaye python 06_index_jev.py --episodes 620-625
    PODCAST=gooaye python 06_index_jev.py --episodes 688 --force
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_podcast_config, get_episode_number_from_filename, parse_episode_range
from src.pipeline import jev_index

podcast = get_podcast_config()


def get_episodes_to_index(ep_start: int | None = None, ep_end: int | None = None, force: bool = False) -> list[str]:
    """Episode ids with both a transcript and a summary, missing an index
    file (or all in range, when --force)."""
    episode_ids = []
    for transcript_file in sorted(podcast.transcript_dir.glob("*.json")):
        episode_id = transcript_file.stem
        ep_num = get_episode_number_from_filename(transcript_file.name)

        if ep_start is not None or ep_end is not None:
            if ep_num is None:
                # Can't range-filter an episode id with no number (e.g. yutinghao).
                continue
            if ep_start is not None and ep_num < ep_start:
                continue
            if ep_end is not None and ep_num > ep_end:
                continue

        summary_file = podcast.summary_dir / f"{episode_id}_summary.txt"
        if not summary_file.exists():
            continue

        index_file = podcast.data_dir / "index" / f"{episode_id}.json"
        if index_file.exists() and not force:
            continue

        episode_ids.append(episode_id)
    return episode_ids


def main():
    parser = argparse.ArgumentParser(
        description="Step 6 (optional): Index episode windows with TypeSafe Jev"
    )
    parser.add_argument(
        "--episodes", type=str, default=None,
        help="Episode range (e.g. '620-625' or '620')"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-index even if an index file already exists"
    )
    args = parser.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        print("WARNING: TYPESAFE_API_KEY not set, skipping Jev index", file=sys.stderr)
        sys.exit(0)

    ep_start, ep_end = None, None
    if args.episodes:
        ep_start, ep_end = parse_episode_range(args.episodes)

    episode_ids = get_episodes_to_index(ep_start, ep_end, force=args.force)

    print("=" * 60)
    print("Jev Index (optional)")
    print("=" * 60)
    print(f"Podcast: {podcast.name}")
    print(f"Episode range: {f'{ep_start}-{ep_end}' if ep_start else 'All missing'}")
    print(f"Force: {args.force}")

    if not episode_ids:
        print("No episodes need Jev indexing.")
        sys.exit(0)

    print(f"Found {len(episode_ids)} episode(s) to index: {episode_ids}")

    indexed, skipped = 0, 0
    for episode_id in episode_ids:
        print(f"\nIndexing {episode_id}...")
        try:
            result = jev_index.index_episode(
                podcast.slug, episode_id, api_key=api_key, data_dir=podcast.data_dir
            )
        except Exception as e:
            print(f"WARNING: Jev index failed for {episode_id}: {e}", file=sys.stderr)
            skipped += 1
            continue
        cost = result["usage"]["cost_usd"]
        print(f"  Indexed {len(result['windows'])} window(s), ${cost:.4f}")
        indexed += 1

    print()
    print("=" * 60)
    print(f"Complete: {indexed} indexed, {skipped} skipped")

    # Optional step: always exit 0, even with per-episode failures above.
    sys.exit(0)


if __name__ == "__main__":
    main()
