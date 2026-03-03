#!/usr/bin/env python3
"""
Step 3: Transcribe audio files using Whisper.

Supports:
- Groq API (whisper-large-v3, fast and free)
- Local faster-whisper (offline)

Reads MP3s from data/{podcast}/audio/ and outputs transcripts to data/{podcast}/transcripts/
Output format matches SpotScribe: [MM:SS] text...

Supports multiple podcasts via PODCAST environment variable.
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from datetime import timedelta
from tqdm import tqdm

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

# Rate limiting for Groq API (free tier: ~20 audio-minutes per hour)
# Reduced from 180s to 60s - exponential backoff handles actual rate limits
# Customizable via GROQ_DELAY_SECONDS env var
GROQ_DELAY_SECONDS = int(os.environ.get("GROQ_DELAY_SECONDS", "60"))
GROQ_MAX_RETRIES = 5  # More retries for rate limits

from src.config import (
    get_podcast_config,
    WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_DEVICE,
    TIMESTAMP_FORMAT, WHISPER_PROVIDER
)

# Get podcast config (from env or default)
podcast = get_podcast_config()


def format_timestamp(seconds: float) -> str:
    """Format seconds to [MM:SS] like SpotScribe."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"[{minutes:02d}:{secs:02d}]"


def convert_to_traditional(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese (Taiwan)."""
    try:
        from opencc import OpenCC
        cc = OpenCC('s2twp')  # Simplified to Traditional (Taiwan with phrases)
        return cc.convert(text)
    except ImportError:
        return text  # Return as-is if opencc not installed


def compress_audio_for_upload(audio_path: Path, max_size_mb: int = 24) -> Path:
    """Compress audio to fit within API limits. Returns path to compressed file."""
    import subprocess
    import tempfile

    file_size_mb = audio_path.stat().st_size / (1024 * 1024)

    if file_size_mb <= max_size_mb:
        return audio_path  # No compression needed

    # Check for required tools
    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe not found. Install ffmpeg: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found. Install ffmpeg: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)")

    # Calculate target bitrate to fit under limit
    # Get duration first
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True
    )

    try:
        duration = float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Failed to get audio duration from {audio_path}. ffprobe output: {result.stderr}")

    if duration <= 0:
        raise RuntimeError(f"Invalid audio duration ({duration}s) for {audio_path}")

    # Target: max_size_mb * 8 * 1024 kbits / duration seconds = bitrate kbps
    target_bitrate = int((max_size_mb * 8 * 1024) / duration * 0.9)  # 90% to be safe
    target_bitrate = max(32, min(target_bitrate, 128))  # Clamp between 32-128 kbps

    # Compress to temp file
    temp_dir = Path(tempfile.gettempdir())
    compressed_path = temp_dir / f"{audio_path.stem}_compressed.mp3"

    subprocess.run([
        "ffmpeg", "-y", "-i", str(audio_path),
        "-ac", "1",  # Mono
        "-ab", f"{target_bitrate}k",
        "-ar", "16000",  # 16kHz sample rate (good for speech)
        str(compressed_path)
    ], capture_output=True, check=True)

    return compressed_path


def transcribe_with_groq(audio_path: Path) -> list[dict]:
    """Transcribe using Groq's Whisper API. Returns segments with timestamps."""
    import httpx

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable not set")

    # Compress if needed (Groq limit is 25MB)
    compressed_path = compress_audio_for_upload(audio_path, max_size_mb=24)
    is_compressed = compressed_path != audio_path

    try:
        url = "https://api.groq.com/openai/v1/audio/transcriptions"

        with open(compressed_path, "rb") as audio_file:
            files = {
                "file": (audio_path.name, audio_file, "audio/mpeg"),
            }
            data = {
                "model": "whisper-large-v3",
                "language": WHISPER_LANGUAGE,
                "response_format": "verbose_json",
                "temperature": 0,
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
            }

            # Use longer timeout for large files
            with httpx.Client(timeout=600.0) as client:
                response = client.post(url, files=files, data=data, headers=headers)
                response.raise_for_status()
                result = response.json()

    finally:
        # Clean up compressed file
        if is_compressed and compressed_path.exists():
            compressed_path.unlink()

    # Parse segments from response and convert to Traditional Chinese
    segments = []
    for seg in result.get("segments", []):
        text = seg.get('text', '').strip()
        text = convert_to_traditional(text)  # Convert to Traditional Chinese
        segments.append({
            'start': seg.get('start', 0),
            'end': seg.get('end', 0),
            'text': text
        })

    # If no segments, create one from full text
    if not segments and result.get("text"):
        text = convert_to_traditional(result.get('text', '').strip())
        segments.append({
            'start': 0,
            'end': result.get('duration', 0),
            'text': text
        })

    return segments


def transcribe_with_faster_whisper(model, audio_path: Path) -> list[dict]:
    """Transcribe using faster-whisper. Returns segments."""
    segments, info = model.transcribe(
        str(audio_path),
        language=WHISPER_LANGUAGE,
        beam_size=5,
        word_timestamps=False,
        vad_filter=True,  # Filter out silence
    )

    results = []
    for segment in segments:
        results.append({
            'start': segment.start,
            'end': segment.end,
            'text': segment.text.strip()
        })
    return results


def transcribe_with_openai_whisper(model, audio_path: Path) -> list[dict]:
    """Transcribe using openai-whisper (local). Returns segments."""
    result = model.transcribe(
        str(audio_path),
        language=WHISPER_LANGUAGE,
        verbose=False
    )

    results = []
    for segment in result['segments']:
        results.append({
            'start': segment['start'],
            'end': segment['end'],
            'text': segment['text'].strip()
        })
    return results


def transcribe_with_openai_api(audio_path: Path) -> list[dict]:
    """Transcribe using OpenAI Whisper API. Returns segments."""
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")

    # Compress if needed (OpenAI limit is 25MB)
    compressed_path = compress_audio_for_upload(audio_path, max_size_mb=24)
    is_compressed = compressed_path != audio_path

    client = openai.OpenAI(api_key=api_key)

    try:
        with open(compressed_path, "rb") as audio_file:
            # Use verbose_json to get timestamps
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=WHISPER_LANGUAGE,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
    finally:
        # Clean up compressed file
        if is_compressed and compressed_path.exists():
            compressed_path.unlink()

    results = []
    for segment in response.segments:
        results.append({
            'start': segment['start'],
            'end': segment['end'],
            'text': segment['text'].strip()
        })
    return results


def format_transcript(segments: list[dict], style: str = 'spotscribe') -> str:
    """Format segments into final transcript text."""
    lines = []
    
    if style == 'spotscribe':
        # SpotScribe style: [MM:SS] text
        for seg in segments:
            timestamp = format_timestamp(seg['start'])
            text = seg['text']
            if text:  # Skip empty segments
                lines.append(f"{timestamp} {text}")
        return '\n'.join(lines)
    
    elif style == 'srt':
        # SRT subtitle format
        for i, seg in enumerate(segments, 1):
            start = str(timedelta(seconds=seg['start'])).replace('.', ',')[:12]
            end = str(timedelta(seconds=seg['end'])).replace('.', ',')[:12]
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(seg['text'])
            lines.append("")
        return '\n'.join(lines)
    
    elif style == 'json':
        # JSON format
        return json.dumps(segments, ensure_ascii=False, indent=2)
    
    else:
        # Plain text
        return '\n'.join(seg['text'] for seg in segments if seg['text'])


def get_episode_number_from_filename(filename: str) -> int | None:
    """Extract episode number from filename like 'EP0621.mp3'."""
    match = re.search(r'EP(\d+)', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def main():
    parser = argparse.ArgumentParser(description="Transcribe podcast audio files")
    parser.add_argument('--force', action='store_true',
                        help="Re-transcribe even if transcript exists")
    parser.add_argument('--ep', type=str, default=None,
                        help="Specific episode or range (e.g., '620' or '615-620')")
    args = parser.parse_args()

    print("=" * 60)
    print(f"Whisper Transcription: {podcast.name}")
    print("=" * 60)

    # Check for audio files
    audio_files = sorted(podcast.audio_dir.glob("*.mp3"))
    if not audio_files:
        print(f"Error: No MP3 files found in {podcast.audio_dir}")
        print("Run 02_download_audio.py first.")
        sys.exit(1)

    print(f"Found {len(audio_files)} audio files")

    # Parse --ep argument if provided
    ep_start, ep_end = podcast.episode_start, podcast.episode_end
    if args.ep:
        try:
            if '-' in args.ep:
                parts = args.ep.split('-')
                ep_start, ep_end = int(parts[0]), int(parts[1])
            else:
                ep_start = ep_end = int(args.ep)
        except ValueError:
            print(f"Error: Invalid episode format '{args.ep}'. Use a number (e.g., '620') or range (e.g., '615-620').")
            return

    # Filter by episode range (only applies to numbered podcasts)
    if ep_start or ep_end:
        audio_files = [
            f for f in audio_files
            if (ep_num := get_episode_number_from_filename(f.name)) and
               (ep_start is None or ep_num >= ep_start) and
               (ep_end is None or ep_num <= ep_end)
        ]
        range_str = f"EP{ep_start}" + (f"-EP{ep_end}" if ep_end else "+")
        print(f"Filtered to {len(audio_files)} files ({range_str})")

    # Create output directory
    podcast.transcript_dir.mkdir(parents=True, exist_ok=True)

    # Check what's already transcribed (unless --force)
    if args.force:
        to_process = audio_files
        print(f"Force mode: will re-transcribe {len(to_process)} files")
    else:
        existing = [
            f for f in audio_files
            if (podcast.transcript_dir / f"{f.stem}.txt").exists()
        ]
        to_process = [f for f in audio_files if f not in existing]
        print(f"Already transcribed: {len(existing)}")
        print(f"To transcribe: {len(to_process)}")
    
    if not to_process:
        print("All episodes already transcribed!")
        return  # Not an error — exit 0

    # Setup transcription function based on provider
    print(f"\nProvider: {WHISPER_PROVIDER}")
    print(f"Model: {WHISPER_MODEL}")

    if WHISPER_PROVIDER == "groq":
        print("Using Groq API (whisper-large-v3)")
        if not os.environ.get("GROQ_API_KEY"):
            print("Error: GROQ_API_KEY environment variable not set")
            sys.exit(1)  # Exit with error code
        transcribe_fn = transcribe_with_groq
    elif WHISPER_PROVIDER == "openai":
        print("Using OpenAI Whisper API (whisper-1)")
        if not os.environ.get("OPENAI_API_KEY"):
            print("Error: OPENAI_API_KEY environment variable not set")
            return
        transcribe_fn = transcribe_with_openai_api
    else:
        # Local whisper
        print(f"Device: {WHISPER_DEVICE}")
        try:
            from faster_whisper import WhisperModel
            USE_FASTER_WHISPER = True
            print("Using faster-whisper")
        except ImportError:
            import whisper
            USE_FASTER_WHISPER = False
            print("Using openai-whisper (local)")

        # Fix model name for local whisper
        local_model = WHISPER_MODEL
        if local_model.startswith("whisper-"):
            local_model = local_model.replace("whisper-", "")  # whisper-large-v3 -> large-v3

        if USE_FASTER_WHISPER:
            model = WhisperModel(
                local_model,
                device=WHISPER_DEVICE,
                compute_type="float16" if WHISPER_DEVICE == "cuda" else "int8"
            )
            transcribe_fn = lambda audio: transcribe_with_faster_whisper(model, audio)
        else:
            model = whisper.load_model(local_model, device=WHISPER_DEVICE)
            transcribe_fn = lambda audio: transcribe_with_openai_whisper(model, audio)

    print("Ready!")
    
    # Process files
    results = {'success': 0, 'failed': 0}
    failed = []
    
    total = len(to_process)
    for i, audio_file in enumerate(to_process):
        output_file = podcast.transcript_dir / f"{audio_file.stem}.txt"
        output_json = podcast.transcript_dir / f"{audio_file.stem}.json"

        # Progress indicator
        progress_pct = int((i / total) * 100)
        print(f"\n[{i+1}/{total}] ({progress_pct}%) Transcribing: {audio_file.stem[:40]}...", flush=True)

        # Rate limiting for Groq API
        if WHISPER_PROVIDER == "groq" and i > 0:
            print(f"  ⏳ Waiting {GROQ_DELAY_SECONDS}s (API rate limit)...", flush=True)
            time.sleep(GROQ_DELAY_SECONDS)

        # Retry logic with exponential backoff
        max_retries = GROQ_MAX_RETRIES if WHISPER_PROVIDER == "groq" else 3
        for attempt in range(max_retries):
            try:
                print(f"  🎙️ Processing audio...", flush=True)
                # Transcribe
                segments = transcribe_fn(audio_file)

                # Save SpotScribe-style text
                transcript_text = format_transcript(segments, style='spotscribe')
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(transcript_text)

                # Also save JSON for later processing
                with open(output_json, 'w', encoding='utf-8') as f:
                    json.dump(segments, f, ensure_ascii=False, indent=2)

                results['success'] += 1
                print(f"  ✅ Done! ({len(transcript_text)} chars)", flush=True)
                break  # Success, exit retry loop

            except Exception as e:
                error_str = str(e)
                if "429" in error_str and attempt < max_retries - 1:
                    # Exponential backoff: 5min, 10min, 15min, 20min...
                    wait_time = 300 * (attempt + 1)  # 5 minutes * attempt
                    print(f"  ⚠️ Rate limited, waiting {wait_time//60}min before retry ({attempt+1}/{max_retries-1})...", flush=True)
                    time.sleep(wait_time)
                else:
                    results['failed'] += 1
                    failed.append({'file': audio_file.name, 'error': error_str})
                    print(f"  ❌ Failed: {e}", flush=True)
                    break
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Transcription Summary")
    print(f"{'=' * 60}")
    print(f"  Success: {results['success']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Output directory: {podcast.transcript_dir}")
    
    if failed:
        print(f"\nFailed files:")
        for f in failed[:5]:
            print(f"  - {f['file']}: {f['error'][:50]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
