#!/usr/bin/env python3
"""
Step 3: Transcribe audio files using Whisper.

Reads MP3s from data/audio/ and outputs transcripts to data/transcripts/
Output format matches SpotScribe: [MM:SS] text...
"""

import json
import re
from pathlib import Path
from datetime import timedelta
from tqdm import tqdm

# Try faster-whisper first (faster), fall back to openai-whisper
try:
    from faster_whisper import WhisperModel
    USE_FASTER_WHISPER = True
    print("Using faster-whisper")
except ImportError:
    import whisper
    USE_FASTER_WHISPER = False
    print("Using openai-whisper (install faster-whisper for 4x speed)")

from config import (
    AUDIO_DIR, TRANSCRIPT_DIR, EPISODES_FILE,
    WHISPER_MODEL, WHISPER_LANGUAGE, WHISPER_DEVICE,
    EPISODE_START, EPISODE_END, TIMESTAMP_FORMAT
)


def format_timestamp(seconds: float) -> str:
    """Format seconds to [MM:SS] like SpotScribe."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"[{minutes:02d}:{secs:02d}]"


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
    """Transcribe using openai-whisper. Returns segments."""
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
    print("=" * 60)
    print("Gooaye Whisper Transcription")
    print("=" * 60)
    
    # Check for audio files
    audio_files = sorted(AUDIO_DIR.glob("*.mp3"))
    if not audio_files:
        print(f"Error: No MP3 files found in {AUDIO_DIR}")
        print("Run 02_download_audio.py first.")
        return
    
    print(f"Found {len(audio_files)} audio files")
    
    # Filter by episode range if configured
    if EPISODE_START or EPISODE_END:
        audio_files = [
            f for f in audio_files
            if (ep_num := get_episode_number_from_filename(f.name)) and
               (EPISODE_START is None or ep_num >= EPISODE_START) and
               (EPISODE_END is None or ep_num <= EPISODE_END)
        ]
        print(f"Filtered to {len(audio_files)} files")
    
    # Create output directory
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check what's already transcribed
    existing = [
        f for f in audio_files
        if (TRANSCRIPT_DIR / f"{f.stem}.txt").exists()
    ]
    to_process = [f for f in audio_files if f not in existing]
    
    print(f"Already transcribed: {len(existing)}")
    print(f"To transcribe: {len(to_process)}")
    
    if not to_process:
        print("All episodes already transcribed!")
        return
    
    # Load model
    print(f"\nLoading Whisper model: {WHISPER_MODEL}")
    print(f"Device: {WHISPER_DEVICE}")
    
    if USE_FASTER_WHISPER:
        model = WhisperModel(
            WHISPER_MODEL, 
            device=WHISPER_DEVICE,
            compute_type="float16" if WHISPER_DEVICE == "cuda" else "int8"
        )
        transcribe_fn = lambda audio: transcribe_with_faster_whisper(model, audio)
    else:
        model = whisper.load_model(WHISPER_MODEL, device=WHISPER_DEVICE)
        transcribe_fn = lambda audio: transcribe_with_openai_whisper(model, audio)
    
    print("Model loaded!")
    
    # Process files
    results = {'success': 0, 'failed': 0}
    failed = []
    
    for audio_file in tqdm(to_process, desc="Transcribing"):
        output_file = TRANSCRIPT_DIR / f"{audio_file.stem}.txt"
        output_json = TRANSCRIPT_DIR / f"{audio_file.stem}.json"
        
        try:
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
            
        except Exception as e:
            results['failed'] += 1
            failed.append({'file': audio_file.name, 'error': str(e)})
            tqdm.write(f"Failed: {audio_file.name} - {e}")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Transcription Summary")
    print(f"{'=' * 60}")
    print(f"  Success: {results['success']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Output directory: {TRANSCRIPT_DIR}")
    
    if failed:
        print(f"\nFailed files:")
        for f in failed[:5]:
            print(f"  - {f['file']}: {f['error'][:50]}")


if __name__ == "__main__":
    main()
