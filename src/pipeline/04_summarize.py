#!/usr/bin/env python3
"""
Step 4: Summarize transcripts using Claude, OpenAI, or Gemini API.

For each transcript in data/{podcast}/transcripts/*.txt that doesn't have a corresponding
summary in data/{podcast}/summaries/, generates a summary in Traditional Chinese.

Supports multiple podcasts via PODCAST environment variable.

Usage:
    python 04_summarize.py                    # Process all missing summaries
    python 04_summarize.py --provider openai  # Use OpenAI instead of Claude
    python 04_summarize.py --model gpt-4o     # Specify model
    python 04_summarize.py --ep 620-625       # Process specific episode range
    python 04_summarize.py --parallel 3       # Process 3 episodes in parallel (faster!)
"""

import argparse
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from src.config import get_podcast_config

# Get podcast config (from env or default)
podcast = get_podcast_config()

# Ensure summary directory exists
podcast.summary_dir.mkdir(parents=True, exist_ok=True)

# Default settings (env var overrides)
DEFAULT_PROVIDER = os.environ.get('SUMMARY_PROVIDER') or "gemini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-4o"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

def get_summary_prompt(transcript: str, episode_number: int | None = None) -> str:
    """Generate podcast-specific summary prompt.

    Checks for custom_prompt.txt in the podcast data directory.
    Supports variables: {podcast_name}, {host}, {transcript}, {episode_number}
    """
    custom_prompt_file = podcast.data_dir / "custom_prompt.txt"

    if custom_prompt_file.exists():
        try:
            template = custom_prompt_file.read_text(encoding='utf-8')
            # Replace variables
            prompt = template.format(
                podcast_name=podcast.name,
                host=podcast.host,
                transcript=transcript,
                episode_number=episode_number or "N/A"
            )
            return prompt
        except Exception as e:
            print(f"  Warning: Error reading custom prompt: {e}")
            # Fall through to default

    # Default prompt
    return f"""Summarize this "{podcast.name}" podcast episode in Traditional Chinese.

Host: {podcast.host}

Include:
- 一句話總結
- 主要討論話題 (bullet points, 詳細說明每個話題)
- 提到的股票/ETF/標的
- {podcast.host} 的觀點或金句

Aim for 400-500 words. Be detailed but concise.

Transcript:
{transcript}"""


def get_episode_number_from_filename(filename: str) -> int | None:
    """Extract episode number from filename like EP0621.txt"""
    match = re.search(r'EP(\d+)', filename)
    return int(match.group(1)) if match else None


def get_transcripts_to_process(ep_start: int | None = None, ep_end: int | None = None) -> list[Path]:
    """Get list of transcripts that need summaries.

    Supports both numbered (EP*.txt) and non-numbered (date-based) podcasts.
    """
    transcripts = []

    # Get all transcript files
    for txt_file in podcast.transcript_dir.glob("*.txt"):
        ep_num = get_episode_number_from_filename(txt_file.name)

        # For numbered episodes, apply episode range filter
        if ep_num is not None:
            if ep_start and ep_num < ep_start:
                continue
            if ep_end and ep_num > ep_end:
                continue
            summary_file = podcast.summary_dir / f"EP{ep_num:04d}_summary.txt"
        else:
            # For non-numbered episodes, use filename-based summary
            summary_file = podcast.summary_dir / f"{txt_file.stem}_summary.txt"

        # Check if summary already exists
        if summary_file.exists():
            continue

        transcripts.append(txt_file)

    # Sort: numbered by EP number, others by filename (date)
    transcripts.sort(key=lambda p: (
        get_episode_number_from_filename(p.name) or 0,
        p.name
    ), reverse=True)
    return transcripts


def summarize_with_anthropic(transcript: str, model: str) -> str:
    """Generate summary using Anthropic Claude API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Please install anthropic: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "user", "content": get_summary_prompt(transcript)}
        ]
    )

    return message.content[0].text


def summarize_with_openai(transcript: str, model: str) -> str:
    """Generate summary using OpenAI API."""
    try:
        import openai
    except ImportError:
        raise ImportError("Please install openai: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    client = openai.OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "user", "content": get_summary_prompt(transcript)}
        ]
    )

    return response.choices[0].message.content


def summarize_with_gemini(transcript: str, model: str) -> str:
    """Generate summary using Google Gemini API (new SDK)."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ImportError("Please install google-genai: pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")

    client = genai.Client(api_key=api_key)

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=get_summary_prompt(transcript))
            ]
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=8192,
    )

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )

    return response.text


def summarize_transcript(transcript_path: Path, provider: str, model: str) -> str:
    """Generate summary for a transcript file."""
    transcript = transcript_path.read_text(encoding="utf-8")
    original_len = len(transcript)

    # Truncate if too long (API limits)
    max_chars = 100000  # ~25k tokens
    if original_len > max_chars:
        truncated_pct = ((original_len - max_chars) / original_len) * 100
        print(f"  ⚠️  Transcript truncated: {original_len:,} → {max_chars:,} chars ({truncated_pct:.1f}% removed)")
        transcript = transcript[:max_chars] + "\n\n[Transcript truncated due to length...]"

    if provider == "anthropic":
        return summarize_with_anthropic(transcript, model)
    elif provider == "openai":
        return summarize_with_openai(transcript, model)
    elif provider == "gemini":
        return summarize_with_gemini(transcript, model)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def parse_episode_range(range_str: str) -> tuple[int | None, int | None]:
    """Parse episode range like '620-625' or '620'."""
    if '-' in range_str:
        parts = range_str.split('-')
        return int(parts[0]), int(parts[1])
    else:
        ep = int(range_str)
        return ep, ep


def process_single_transcript(
    transcript_path: Path,
    provider: str,
    model: str,
    index: int,
    total: int
) -> dict:
    """Process a single transcript. Returns result dict for parallel execution."""
    ep_num = get_episode_number_from_filename(transcript_path.name)

    # Display name and determine summary filename
    if ep_num:
        display_name = f"EP{ep_num:04d}"
        summary_file = podcast.summary_dir / f"EP{ep_num:04d}_summary.txt"
    else:
        display_name = transcript_path.stem[:30]
        summary_file = podcast.summary_dir / f"{transcript_path.stem}_summary.txt"

    result = {
        "transcript": transcript_path,
        "display_name": display_name,
        "success": False,
        "error": None,
        "chars": 0
    }

    try:
        summary = summarize_transcript(transcript_path, provider, model)
        summary_file.write_text(summary, encoding="utf-8")
        result["success"] = True
        result["chars"] = len(summary)
    except Exception as e:
        result["error"] = str(e)

    return result


def main():
    parser = argparse.ArgumentParser(description="Summarize Gooaye transcripts")
    parser.add_argument('--provider', choices=['anthropic', 'openai', 'gemini'],
                        default=DEFAULT_PROVIDER,
                        help=f"API provider (default: {DEFAULT_PROVIDER})")
    parser.add_argument('--model', type=str, default=None,
                        help="Model to use (default: provider-specific)")
    parser.add_argument('--ep', type=str, default=None,
                        help="Episode range (e.g., '620-625' or '620')")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be processed without actually calling API")
    parser.add_argument('--parallel', '-p', type=int, default=1, metavar='N',
                        help="Number of parallel workers (default: 1, max: 5)")
    args = parser.parse_args()

    # Clamp parallel workers to safe range
    args.parallel = max(1, min(5, args.parallel))

    # Set default model based on provider
    if args.model is None:
        if args.provider == "anthropic":
            args.model = DEFAULT_ANTHROPIC_MODEL
        elif args.provider == "openai":
            args.model = DEFAULT_OPENAI_MODEL
        else:
            args.model = DEFAULT_GEMINI_MODEL

    # Parse episode range
    ep_start, ep_end = None, None
    if args.ep:
        ep_start, ep_end = parse_episode_range(args.ep)

    print("=" * 60)
    print("Gooaye Transcript Summarizer")
    print("=" * 60)
    print(f"Provider: {args.provider}")
    print(f"Model: {args.model}")
    print(f"Episode range: {f'EP{ep_start}-EP{ep_end}' if ep_start else 'All'}")
    print(f"Parallel workers: {args.parallel}")
    print(f"Output directory: {podcast.summary_dir}")
    print()

    # Get transcripts to process
    transcripts = get_transcripts_to_process(ep_start, ep_end)

    if not transcripts:
        print("No transcripts need summarization.")
        return

    print(f"Found {len(transcripts)} transcript(s) to summarize:")
    for t in transcripts[:10]:
        print(f"  - {t.name}")
    if len(transcripts) > 10:
        print(f"  ... and {len(transcripts) - 10} more")
    print()

    if args.dry_run:
        print("Dry run - no API calls made.")
        return

    # Process transcripts
    success_count = 0
    error_count = 0
    total = len(transcripts)
    start_time = time.time()

    if args.parallel > 1:
        # Parallel processing
        print(f"Using {args.parallel} parallel workers...")
        print()

        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            # Submit all tasks with staggered start to avoid rate limit burst
            futures = {}
            for i, transcript_path in enumerate(transcripts):
                future = executor.submit(
                    process_single_transcript,
                    transcript_path,
                    args.provider,
                    args.model,
                    i + 1,
                    total
                )
                futures[future] = transcript_path
                # Small delay between submissions to avoid rate limit burst
                if i < len(transcripts) - 1:
                    time.sleep(0.5)

            # Collect results as they complete
            for future in as_completed(futures):
                result = future.result()
                if result["success"]:
                    print(f"  ✅ {result['display_name']} ({result['chars']} chars)")
                    success_count += 1
                else:
                    print(f"  ❌ {result['display_name']}: {result['error']}")
                    error_count += 1
    else:
        # Sequential processing (original behavior)
        for i, transcript_path in enumerate(transcripts, 1):
            ep_num = get_episode_number_from_filename(transcript_path.name)

            if ep_num:
                display_name = f"EP{ep_num:04d}"
                summary_file = podcast.summary_dir / f"EP{ep_num:04d}_summary.txt"
            else:
                display_name = transcript_path.stem[:30]
                summary_file = podcast.summary_dir / f"{transcript_path.stem}_summary.txt"

            progress_pct = int((i / total) * 100)
            print(f"\n[{i}/{total}] ({progress_pct}%) Summarizing {display_name}...", flush=True)

            try:
                print(f"  Generating summary...", flush=True)
                summary = summarize_transcript(transcript_path, args.provider, args.model)
                summary_file.write_text(summary, encoding="utf-8")
                print(f"  ✅ Done! ({len(summary)} chars)", flush=True)
                success_count += 1
            except Exception as e:
                print(f"  ❌ ERROR: {e}", flush=True)
                error_count += 1

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print(f"Complete: {success_count} succeeded, {error_count} failed")
    print(f"Time: {elapsed:.1f}s ({elapsed/max(1,success_count+error_count):.1f}s per episode)")
    print(f"Summaries saved to: {podcast.summary_dir}")


if __name__ == "__main__":
    main()
