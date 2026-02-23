#!/usr/bin/env python3
"""
Step 5: Generate social media drafts from AI summaries.

For each summary in data/{podcast}/summaries/*.txt that doesn't have a corresponding
draft in data/{podcast}/social_drafts/, generates platform-specific content.

Platforms: Twitter (thread), Threads (single post), LINE, Instagram (image card), Telegram

Usage:
    python 05_generate_social.py                    # Process all missing drafts
    python 05_generate_social.py --ep 620-625      # Process specific episode range
    python 05_generate_social.py --regenerate       # Regenerate existing drafts
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_podcast_config, get_episode_number_from_filename
from social.formatters import TwitterFormatter, ThreadsFormatter, LineFormatter, InstagramFormatter, TelegramFormatter
from social.formatters.base import SummaryContent
from social.draft import DraftManager, SocialDraft
from social.image_generator import InstagramCardGenerator


# Get podcast config (from env or default)
podcast = get_podcast_config()

# Initialize formatters
formatters = {
    "twitter": TwitterFormatter(),
    "threads": ThreadsFormatter(),
    "line": LineFormatter(),
    "instagram": InstagramFormatter(),
    "telegram": TelegramFormatter(),
}


def get_summary_hash(summary_path: Path) -> str:
    """Get hash of summary file for change detection."""
    content = summary_path.read_text(encoding="utf-8")
    return hashlib.md5(content.encode()).hexdigest()[:12]


def get_summaries_to_process(
    ep_start: int | None = None,
    ep_end: int | None = None,
    regenerate: bool = False
) -> list[Path]:
    """Get list of summaries that need social drafts."""
    draft_manager = DraftManager(podcast.data_dir)
    summaries = []

    for summary_file in podcast.summary_dir.glob("*_summary.txt"):
        ep_num = get_episode_number_from_filename(summary_file.name)
        episode_id = f"EP{ep_num:04d}" if ep_num else summary_file.stem.replace("_summary", "")

        # Apply episode range filter
        if ep_num is not None:
            if ep_start and ep_num < ep_start:
                continue
            if ep_end and ep_num > ep_end:
                continue

        # Check if draft exists
        existing_draft = draft_manager.get_draft(episode_id)

        if existing_draft and not regenerate:
            # Check if summary changed
            current_hash = get_summary_hash(summary_file)
            if existing_draft.summary_hash == current_hash:
                continue

        summaries.append(summary_file)

    # Sort by episode number (newest first)
    summaries.sort(key=lambda p: (
        get_episode_number_from_filename(p.name) or 0,
        p.name
    ), reverse=True)

    return summaries


def generate_drafts(summary_path: Path) -> SocialDraft | None:
    """Generate social drafts from a summary file."""
    ep_num = get_episode_number_from_filename(summary_path.name)
    episode_id = f"EP{ep_num:04d}" if ep_num else summary_path.stem.replace("_summary", "")

    print(f"  Parsing summary content...")

    # Parse summary content
    content = SummaryContent.from_summary_file(
        summary_path,
        episode_id=episode_id,
        podcast_name=podcast.name,
        host=podcast.host
    )

    # Create draft
    draft = SocialDraft(
        episode_id=episode_id,
        podcast=podcast.slug,
        summary_hash=get_summary_hash(summary_path)
    )

    draft_manager = DraftManager(podcast.data_dir)

    # Generate content for each platform
    for platform_name, formatter in formatters.items():
        print(f"  Generating {platform_name} content...")
        try:
            formatted = formatter.format(content)
            draft_manager.save_platform_content(episode_id, platform_name, formatted)
            draft.platforms[platform_name].status = "pending"
        except Exception as e:
            print(f"    Warning: Failed to generate {platform_name}: {e}")
            draft.platforms[platform_name].status = "failed"
            draft.platforms[platform_name].error = str(e)

    # Generate Instagram image card
    try:
        print(f"  Generating Instagram image card...")
        ig_content = draft_manager.get_platform_content(episode_id, "instagram")
        if ig_content:
            image_config = ig_content.get("image_config", {})
            generator = InstagramCardGenerator()
            image_path = draft_manager.get_draft_dir(episode_id) / "instagram_card.png"
            generator.generate(image_config, image_path)
            draft.platforms["instagram"].image_file = "instagram_card.png"
    except Exception as e:
        print(f"    Warning: Failed to generate IG image: {e}")

    # Save draft metadata
    draft_manager.save_draft(draft)
    return draft


def parse_episode_range(range_str: str) -> tuple[int | None, int | None]:
    """Parse episode range like '620-625' or '620'."""
    if '-' in range_str:
        parts = range_str.split('-')
        return int(parts[0]), int(parts[1])
    else:
        ep = int(range_str)
        return ep, ep


def main():
    parser = argparse.ArgumentParser(description="Generate social media drafts from summaries")
    parser.add_argument('--ep', type=str, default=None,
                        help="Episode range (e.g., '620-625' or '620')")
    parser.add_argument('--regenerate', action='store_true',
                        help="Regenerate existing drafts")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be processed without generating")
    args = parser.parse_args()

    # Parse episode range
    ep_start, ep_end = None, None
    if args.ep:
        ep_start, ep_end = parse_episode_range(args.ep)

    print("=" * 60)
    print("Social Draft Generator")
    print("=" * 60)
    print(f"Podcast: {podcast.name}")
    print(f"Episode range: {f'EP{ep_start}-EP{ep_end}' if ep_start else 'All'}")
    print(f"Regenerate: {args.regenerate}")
    print(f"Output directory: {podcast.data_dir / 'social_drafts'}")
    print()

    # Get summaries to process
    summaries = get_summaries_to_process(ep_start, ep_end, args.regenerate)

    if not summaries:
        print("No summaries need social draft generation.")
        return

    print(f"Found {len(summaries)} summary(s) to process:")
    for s in summaries[:10]:
        print(f"  - {s.name}")
    if len(summaries) > 10:
        print(f"  ... and {len(summaries) - 10} more")
    print()

    if args.dry_run:
        print("Dry run - no drafts generated.")
        return

    # Process each summary
    success_count = 0
    error_count = 0

    for i, summary_path in enumerate(summaries, 1):
        ep_num = get_episode_number_from_filename(summary_path.name)
        display_name = f"EP{ep_num:04d}" if ep_num else summary_path.stem[:20]

        progress_pct = int((i / len(summaries)) * 100)
        print(f"\n[{i}/{len(summaries)}] ({progress_pct}%) Generating drafts for {display_name}...")

        try:
            draft = generate_drafts(summary_path)
            if draft:
                print(f"  ✅ Done!")
                success_count += 1
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            error_count += 1

    print()
    print("=" * 60)
    print(f"Complete: {success_count} succeeded, {error_count} failed")
    print(f"Drafts saved to: {podcast.data_dir / 'social_drafts'}")


if __name__ == "__main__":
    main()
