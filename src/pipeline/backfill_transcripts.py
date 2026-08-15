#!/usr/bin/env python3
"""Backfill existing transcripts: Traditional Chinese + ASR term corrections.

Not a numbered pipeline step - a maintenance tool for transcripts written
before those two fixes landed (see src/config.apply_term_corrections).

Both operations are idempotent, so re-running is safe.

    ./venv/bin/python src/pipeline/backfill_transcripts.py --dry-run
    ./venv/bin/python src/pipeline/backfill_transcripts.py --podcast gooaye
    ./venv/bin/python src/pipeline/backfill_transcripts.py --episodes 685-688
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import (
    PODCASTS, get_podcast_config, get_episode_number_from_filename,
    parse_episode_range, normalize_transcript_text as normalize,
)


def in_range(path: Path, ep_range) -> bool:
    if ep_range is None:
        return True
    number = get_episode_number_from_filename(path.name)
    if number is None:
        return False
    return ep_range[0] <= number <= ep_range[1]


def backfill_txt(path: Path, dry_run: bool) -> bool:
    original = path.read_text(encoding='utf-8')

    # Per line, never whole-file: the Simplified gate needs zero
    # Traditional-only characters, and any full episode has some somewhere.
    # Normalizing the file as one string silently converts nothing.
    fixed = '\n'.join(normalize(line) for line in original.split('\n'))

    if fixed == original:
        return False
    if not dry_run:
        path.write_text(fixed, encoding='utf-8')
    return True


def backfill_json(path: Path, dry_run: bool) -> bool:
    try:
        segments = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        print(f"  SKIP {path.name}: invalid JSON ({e})", file=sys.stderr)
        return False

    changed = False
    for seg in segments:
        fixed = normalize(seg.get('text', ''))
        if fixed != seg.get('text'):
            seg['text'] = fixed
            changed = True

    if changed and not dry_run:
        path.write_text(
            json.dumps(segments, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--podcast', help="Only this podcast (default: all)")
    parser.add_argument('--episodes', help="Episode or range, e.g. 685 or 685-688")
    parser.add_argument('--dry-run', action='store_true',
                        help="Report what would change, write nothing")
    args = parser.parse_args()

    try:
        normalize("测试")
    except ImportError:
        sys.exit("ERROR: opencc not installed. pip install opencc-python-reimplemented")

    ep_range = parse_episode_range(args.episodes) if args.episodes else None
    slugs = [args.podcast] if args.podcast else list(PODCASTS)

    total = 0
    for slug in slugs:
        podcast = get_podcast_config(slug)
        files = sorted(
            f for f in podcast.transcript_dir.iterdir()
            if f.suffix in ('.txt', '.json') and in_range(f, ep_range)
        )
        if not files:
            continue

        print(f"\n{slug}: checking {len(files)} file(s)")
        for path in files:
            handler = backfill_json if path.suffix == '.json' else backfill_txt
            if handler(path, args.dry_run):
                total += 1
                print(f"  {'would fix' if args.dry_run else 'fixed'} {path.name}")

    verb = "would change" if args.dry_run else "changed"
    print(f"\n{verb} {total} file(s)")


if __name__ == "__main__":
    main()
