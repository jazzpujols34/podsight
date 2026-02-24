#!/usr/bin/env python3
"""
PodSight - AI Podcast Summarization Pipeline

Entry point for running the server or pipeline.

Usage:
    python main.py                     # Start web server (default)
    python main.py serve               # Start web server
    python main.py serve --port 8080   # Custom port

    python main.py pipeline            # Run full pipeline for default podcast
    python main.py pipeline -p gooaye  # Run for specific podcast
    python main.py pipeline --step 1   # Run specific step only
    python main.py pipeline --list     # List available podcasts
"""

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def check_dependencies():
    """Check if required packages are installed."""
    missing = []
    try:
        import fastapi
    except ImportError:
        missing.append("fastapi")
    try:
        import uvicorn
    except ImportError:
        missing.append("uvicorn")
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        sys.exit(1)


def cmd_serve(args):
    """Start the web server."""
    check_dependencies()

    url = f"http://{args.host}:{args.port}"

    print("=" * 50)
    print("   PodSight 聲見 - AI Podcast Summaries")
    print("=" * 50)
    print()
    print(f"   URL: {url}")
    print(f"   API Docs: {url}/docs")
    print()
    print("   Press Ctrl+C to stop")
    print("=" * 50)
    print()

    # Open browser after delay
    if not args.no_browser:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)
        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    import uvicorn
    uvicorn.run(
        "src.server:app",
        host=args.host,
        port=args.port,
        log_level="info"
    )


def cmd_pipeline(args):
    """Run the podcast pipeline."""
    from src.config import list_podcasts, get_podcast_config

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

    pipeline_dir = Path(__file__).parent / "src" / "pipeline"

    def run_step(step_num: int, script_name: str):
        print(f"\n{'#' * 60}")
        print(f"# Step {step_num}: {script_name}")
        print(f"{'#' * 60}\n")

        script_path = pipeline_dir / script_name
        env = {**os.environ, 'PODCAST': podcast.slug}
        result = subprocess.run([sys.executable, str(script_path)], env=env)

        if result.returncode != 0:
            print(f"\nStep {step_num} failed with code {result.returncode}")
            return False
        return True

    if args.step:
        step = next((s for s in steps if s[0] == args.step), None)
        if step:
            run_step(step[0], step[1])
    else:
        print("=" * 60)
        print(f"Podcast Pipeline: {podcast.name}")
        print("=" * 60)
        print("\nThis will:")
        print("  1. Parse RSS feed to get episode list")
        print("  2. Download all audio files")
        print("  3. Transcribe with Whisper")
        print("  4. Summarize transcripts with AI")
        print(f"\nData directory: {podcast.data_dir}")
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


def main():
    parser = argparse.ArgumentParser(
        description="PodSight - AI Podcast Summarization",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start web server")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host (default: 127.0.0.1)")
    serve_parser.add_argument("--no-browser", action="store_true", help="Don't open browser")

    # Pipeline command
    pipeline_parser = subparsers.add_parser("pipeline", help="Run transcription pipeline")
    pipeline_parser.add_argument("-p", "--podcast", type=str, help="Podcast slug")
    pipeline_parser.add_argument("--step", type=int, choices=[1, 2, 3, 4], help="Run specific step")
    pipeline_parser.add_argument("--list", "-l", action="store_true", help="List podcasts")

    args = parser.parse_args()

    # Default to serve if no command
    if args.command is None:
        args.command = "serve"
        args.port = 8000
        args.host = "127.0.0.1"
        args.no_browser = False

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "pipeline":
        cmd_pipeline(args)


if __name__ == "__main__":
    main()
