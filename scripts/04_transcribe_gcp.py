#!/usr/bin/env python3
"""
Step 3b: Transcribe audio using Google Cloud Speech-to-Text API.

Much faster and higher quality than local Whisper:
- 10-15x faster than Whisper on CPU
- Professional-grade accuracy
- Automatic punctuation
- Cost: ~$0.024 per minute of audio

Output: data/transcripts/{EP}.txt with SpotScribe-compatible timestamps
"""

import json
import os
import sys
from pathlib import Path
from tqdm import tqdm
from google.cloud import speech_v1
from google.oauth2 import service_account
import io

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AUDIO_DIR, TRANSCRIPT_DIR, EPISODES_FILE, EPISODE_START, EPISODE_END, TIMESTAMP_FORMAT

def load_episodes_list() -> list[dict]:
    """Load episodes from the episodes.json file."""
    if not EPISODES_FILE.exists():
        print(f"Error: {EPISODES_FILE} not found. Run 01_parse_rss.py first.")
        sys.exit(1)

    with open(EPISODES_FILE, 'r', encoding='utf-8') as f:
        episodes = json.load(f)
    return episodes

def get_gcp_client():
    """Initialize GCP Speech-to-Text client with credentials."""
    # Look for credentials JSON
    key_path = Path(__file__).parent / "gcp-key.json"

    if not key_path.exists():
        print(f"\n⚠️  ERROR: GCP credentials not found!")
        print(f"   Expected: {key_path}")
        print(f"\n   To set up:")
        print(f"   1. Go to GCP Console → Credentials")
        print(f"   2. Create Service Account with 'Cloud Speech Client' role")
        print(f"   3. Create JSON key and download")
        print(f"   4. Save as: {key_path}")
        print(f"   5. Enable Speech-to-Text API")
        sys.exit(1)

    # Create credentials from JSON file
    credentials = service_account.Credentials.from_service_account_file(
        str(key_path)
    )

    # Create client with credentials
    client = speech_v1.SpeechClient(credentials=credentials)
    return client

def transcribe_audio_gcp(audio_path: Path, client) -> list[dict]:
    """Transcribe audio file using Google Cloud Speech-to-Text API."""

    print(f"  Uploading and transcribing {audio_path.name}...")

    # Read audio file
    with open(audio_path, 'rb') as audio_file:
        content = audio_file.read()

    # Prepare audio
    audio = speech_v1.RecognitionAudio(content=content)

    # Configure transcription
    config = speech_v1.RecognitionConfig(
        encoding=speech_v1.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=48000,
        language_code="zh-CN",  # Simplified Chinese
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,  # Get timestamps for each word
        model="latest_long",  # Best for long audio
    )

    # Call Google Cloud Speech API
    response = client.recognize(config=config, audio=audio)

    # Extract results with timestamps
    results = []
    for result in response.results:
        for alternative in result.alternatives:
            for word_info in alternative.words:
                if word_info.word.strip():
                    # Convert time to MM:SS format
                    start_time = word_info.start_time.total_seconds()
                    minutes = int(start_time // 60)
                    seconds = int(start_time % 60)
                    timestamp = TIMESTAMP_FORMAT.format(minutes=minutes, seconds=seconds)

                    results.append({
                        'timestamp': timestamp,
                        'start_time': start_time,
                        'text': word_info.word,
                        'confidence': alternative.confidence
                    })

    return results

def merge_results_into_lines(results: list[dict], max_chars_per_line: int = 60) -> list[str]:
    """Merge word-level results into lines with timestamps."""
    if not results:
        return []

    lines = []
    current_line = ""
    current_timestamp = results[0]['timestamp']

    for item in results:
        # Start new line if timestamp changes or line is getting too long
        if (item['timestamp'] != current_timestamp and current_line.strip()) or len(current_line) > max_chars_per_line:
            lines.append(f"{current_timestamp} {current_line.strip()}")
            current_line = ""
            current_timestamp = item['timestamp']

        current_line += item['text']

    # Add last line
    if current_line.strip():
        lines.append(f"{current_timestamp} {current_line.strip()}")

    return lines

def transcribe_file(audio_path: Path, client) -> bool:
    """Transcribe a single audio file."""
    try:
        # Get episode number from filename
        ep_num = audio_path.stem

        # Skip if already transcribed
        transcript_path = TRANSCRIPT_DIR / f"{ep_num}.txt"
        if transcript_path.exists():
            print(f"  ✓ {ep_num} already transcribed, skipping")
            return True

        # Transcribe with GCP
        results = transcribe_audio_gcp(audio_path, client)

        if not results:
            print(f"  ✗ {ep_num} no results returned")
            return False

        # Merge results into lines
        lines = merge_results_into_lines(results)

        # Save transcript
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        with open(transcript_path, 'w', encoding='utf-8') as f:
            for line in lines:
                f.write(line + '\n')

        # Also save JSON for reference
        json_path = TRANSCRIPT_DIR / f"{ep_num}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'episode': ep_num,
                'lines': lines,
                'word_count': sum(len(line.split()) for line in lines),
            }, f, ensure_ascii=False, indent=2)

        print(f"  ✓ {ep_num} transcribed ({len(lines)} lines)")
        return True

    except Exception as e:
        print(f"  ✗ {ep_num} failed: {str(e)}")
        return False

def calculate_cost(total_seconds: int) -> float:
    """Calculate estimated cost for GCP transcription."""
    # Google Cloud Speech-to-Text: $0.024 per minute
    minutes = total_seconds / 60
    cost = minutes * 0.024
    return cost

def main():
    print("=" * 60)
    print("Gooaye GCP Speech-to-Text Transcription")
    print("=" * 60)

    # Load episodes
    episodes = load_episodes_list()
    print(f"Loaded {len(episodes)} episodes from {EPISODES_FILE}")

    # Filter by episode range
    if EPISODE_START or EPISODE_END:
        start = EPISODE_START or 1
        end = EPISODE_END or 624
        filtered = [e for e in episodes if e['episode_number'] and start <= e['episode_number'] <= end]
        print(f"Filtered to {len(filtered)} episodes (EP{start} - EP{end})")
    else:
        filtered = episodes

    # Find audio files that need transcription
    audio_files = list(AUDIO_DIR.glob("EP*.mp3"))
    to_transcribe = [f for f in audio_files if (TRANSCRIPT_DIR / f"{f.stem}.txt").exists() == False]

    print(f"\nAudio files found: {len(audio_files)}")
    print(f"Already transcribed: {len(audio_files) - len(to_transcribe)}")
    print(f"To transcribe: {len(to_transcribe)}")

    if not to_transcribe:
        print("✓ All episodes already transcribed!")
        return

    # Calculate cost
    total_seconds = sum(e['duration_seconds'] for e in filtered if e['episode_number'])
    cost = calculate_cost(total_seconds)
    print(f"\nEstimated cost: ${cost:.2f} ({total_seconds // 3600}h {(total_seconds % 3600) // 60}m of audio)")

    # Initialize GCP client
    print("\nInitializing Google Cloud Speech-to-Text client...")
    client = get_gcp_client()
    print("✓ GCP client ready!")

    # Transcribe files
    print(f"\nTranscribing {len(to_transcribe)} episodes...")
    success_count = 0
    failed_count = 0

    for audio_file in tqdm(to_transcribe, desc="Transcribing"):
        if transcribe_file(audio_file, client):
            success_count += 1
        else:
            failed_count += 1

    # Summary
    print("\n" + "=" * 60)
    print("Transcription Summary")
    print("=" * 60)
    print(f"  Success: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Output directory: {TRANSCRIPT_DIR}")
    print(f"  Cost estimate: ${cost:.2f}")

if __name__ == "__main__":
    main()
