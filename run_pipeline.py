#!/usr/bin/env python3
"""
Run the complete Gooaye transcription pipeline.

Usage:
    python run_pipeline.py           # Run all steps
    python run_pipeline.py --step 1  # Run only step 1 (parse RSS)
    python run_pipeline.py --step 2  # Run only step 2 (download)
    python run_pipeline.py --step 3  # Run only step 3 (transcribe)
    python run_pipeline.py --from 295 --to 624  # Process EP295-EP624 only
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_step(step_num: int, script_name: str):
    """Run a pipeline step."""
    print(f"\n{'#' * 60}")
    print(f"# Step {step_num}: {script_name}")
    print(f"{'#' * 60}\n")
    
    script_path = Path(__file__).parent / script_name
    result = subprocess.run([sys.executable, str(script_path)])
    
    if result.returncode != 0:
        print(f"\nStep {step_num} failed with code {result.returncode}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Gooaye transcription pipeline")
    parser.add_argument('--step', type=int, choices=[1, 2, 3], 
                        help="Run only specific step")
    parser.add_argument('--from', dest='ep_start', type=int,
                        help="Start from episode number")
    parser.add_argument('--to', dest='ep_end', type=int,
                        help="End at episode number")
    args = parser.parse_args()
    
    # Update config if episode range specified
    if args.ep_start or args.ep_end:
        config_path = Path(__file__).parent / "config.py"
        config_content = config_path.read_text()
        
        if args.ep_start:
            config_content = config_content.replace(
                "EPISODE_START = None",
                f"EPISODE_START = {args.ep_start}"
            )
        if args.ep_end:
            config_content = config_content.replace(
                "EPISODE_END = None",
                f"EPISODE_END = {args.ep_end}"
            )
        
        config_path.write_text(config_content)
        print(f"Updated config: EP{args.ep_start or 1} - EP{args.ep_end or 'latest'}")
    
    steps = [
        (1, "01_parse_rss.py"),
        (2, "02_download_audio.py"),
        (3, "03_transcribe.py"),
    ]
    
    if args.step:
        # Run single step
        step = next((s for s in steps if s[0] == args.step), None)
        if step:
            run_step(*step)
    else:
        # Run all steps
        print("=" * 60)
        print("Gooaye Transcription Pipeline")
        print("=" * 60)
        print("\nThis will:")
        print("  1. Parse RSS feed to get episode list")
        print("  2. Download all audio files")
        print("  3. Transcribe with Whisper")
        print("\nEstimated time: 20-50 hours depending on hardware")
        print("\nPress Ctrl+C to cancel, or Enter to continue...")
        
        try:
            input()
        except KeyboardInterrupt:
            print("\nCancelled.")
            return
        
        for step_num, script_name in steps:
            if not run_step(step_num, script_name):
                print(f"\nPipeline stopped at step {step_num}")
                return
        
        print("\n" + "=" * 60)
        print("Pipeline complete!")
        print("=" * 60)
        print("\nTranscripts saved to: data/transcripts/")


if __name__ == "__main__":
    main()
