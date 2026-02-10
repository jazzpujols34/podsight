#!/usr/bin/env python3
"""
Run the complete podcast transcription pipeline.

Usage:
    python run_pipeline.py                    # Run all steps for default podcast
    python run_pipeline.py --podcast gooaye   # Run for specific podcast
    python run_pipeline.py --podcast zhaohua  # Run for 兆華與股惑仔
    python run_pipeline.py --step 1           # Run only step 1 (parse RSS)
    python run_pipeline.py --step 2           # Run only step 2 (download)
    python run_pipeline.py --step 3           # Run only step 3 (transcribe)
    python run_pipeline.py --step 4           # Run only step 4 (summarize)
    python run_pipeline.py --list             # List available podcasts
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from config import list_podcasts, get_podcast_config


def run_step(step_num: int, script_name: str, podcast_slug: str):
    """Run a pipeline step with podcast context."""
    print(f"\n{'#' * 60}")
    print(f"# Step {step_num}: {script_name}")
    print(f"{'#' * 60}\n")

    script_path = Path(__file__).parent / script_name
    env = {**os.environ, 'PODCAST': podcast_slug}
    result = subprocess.run([sys.executable, str(script_path)], env=env)

    if result.returncode != 0:
        print(f"\nStep {step_num} failed with code {result.returncode}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Podcast transcription pipeline")
    parser.add_argument('--podcast', '-p', type=str,
                        help="Podcast slug (e.g., gooaye, yutinghao, zhaohua)")
    parser.add_argument('--step', type=int, choices=[1, 2, 3, 4],
                        help="Run only specific step")
    parser.add_argument('--list', '-l', action='store_true',
                        help="List available podcasts")
    args = parser.parse_args()

    # List podcasts
    if args.list:
        print("Available podcasts:")
        for slug, name in list_podcasts().items():
            default = " (default)" if slug == "gooaye" else ""
            print(f"  {slug}: {name}{default}")
        return

    # Get podcast config
    podcast = get_podcast_config(args.podcast)
    print(f"Podcast: {podcast.name} ({podcast.slug})")
    
    steps = [
        (1, "01_parse_rss.py"),
        (2, "02_download_audio.py"),
        (3, "03_transcribe.py"),
        (4, "04_summarize.py"),
    ]

    if args.step:
        # Run single step
        step = next((s for s in steps if s[0] == args.step), None)
        if step:
            run_step(step[0], step[1], podcast.slug)
    else:
        # Run all steps
        print("=" * 60)
        print(f"Podcast Pipeline: {podcast.name}")
        print("=" * 60)
        print("\nThis will:")
        print("  1. Parse RSS feed to get episode list")
        print("  2. Download all audio files")
        print("  3. Transcribe with Whisper")
        print("  4. Summarize transcripts with AI (requires API key)")
        print(f"\nData directory: {podcast.data_dir}")
        print("\nPress Ctrl+C to cancel, or Enter to continue...")

        try:
            input()
        except KeyboardInterrupt:
            print("\nCancelled.")
            return

        for step_num, script_name in steps:
            if not run_step(step_num, script_name, podcast.slug):
                print(f"\nPipeline stopped at step {step_num}")
                return

        print("\n" + "=" * 60)
        print("Pipeline complete!")
        print("=" * 60)
        print(f"\nTranscripts saved to: {podcast.transcript_dir}")


if __name__ == "__main__":
    main()
