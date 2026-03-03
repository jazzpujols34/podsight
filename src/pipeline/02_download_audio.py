#!/usr/bin/env python3
"""
Step 2: Download audio files for all episodes.

Reads from data/{podcast}/episodes.json and downloads MP3s to data/{podcast}/audio/

Supports multiple podcasts via PODCAST environment variable.
"""

import json
import sys
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import get_podcast_config, DOWNLOAD_WORKERS, DOWNLOAD_RETRY

# Get podcast config (from env or default)
podcast = get_podcast_config()

def sanitize_filename(title: str, ep_num: int | None) -> str:
    """Create a safe filename from episode title."""
    if ep_num:
        return f"EP{ep_num:04d}.mp3"
    # Fallback: sanitize title
    safe = "".join(c if c.isalnum() or c in ' -_' else '_' for c in title)
    return f"{safe[:50]}.mp3"

def download_episode(episode: dict, output_dir: Path) -> dict:
    """Download a single episode. Returns status dict."""
    ep_num = episode.get('episode_number')
    title = episode.get('title', 'Unknown')
    audio_url = episode.get('audio_url')
    
    if not audio_url:
        return {'episode': ep_num, 'status': 'skipped', 'reason': 'no audio URL'}
    
    filename = sanitize_filename(title, ep_num)
    output_path = output_dir / filename
    
    # Skip if already downloaded
    if output_path.exists():
        return {'episode': ep_num, 'status': 'exists', 'path': str(output_path)}
    
    # Download with retries
    for attempt in range(DOWNLOAD_RETRY):
        try:
            response = requests.get(audio_url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Get file size for progress
            total_size = int(response.headers.get('content-length', 0))
            
            # Download in chunks
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return {
                'episode': ep_num, 
                'status': 'success', 
                'path': str(output_path),
                'size_mb': output_path.stat().st_size / (1024 * 1024)
            }
            
        except Exception as e:
            if attempt == DOWNLOAD_RETRY - 1:
                return {'episode': ep_num, 'status': 'failed', 'error': str(e)}
            continue
    
    return {'episode': ep_num, 'status': 'failed', 'error': 'max retries exceeded'}

def main():
    print("=" * 60)
    print(f"Audio Downloader: {podcast.name}")
    print("=" * 60)

    # Load episodes
    if not podcast.episodes_file.exists():
        print(f"Error: {podcast.episodes_file} not found. Run 01_parse_rss.py first.")
        sys.exit(1)

    with open(podcast.episodes_file, 'r', encoding='utf-8') as f:
        episodes = json.load(f)

    print(f"Loaded {len(episodes)} episodes from {podcast.episodes_file}")

    # Filter by episode range if configured (for numbered podcasts like Gooaye)
    ep_start = podcast.episode_start or 1
    ep_end = podcast.episode_end  # None means no upper limit
    if podcast.episode_start or podcast.episode_end:
        original_count = len(episodes)
        episodes = [
            e for e in episodes
            if e.get('episode_number') is not None and
               e['episode_number'] >= ep_start and
               (ep_end is None or e['episode_number'] <= ep_end)
        ]
        print(f"Filtered to {len(episodes)} episodes (EP{ep_start} - EP{ep_end or 'latest'})")

    # Create output directory
    podcast.audio_dir.mkdir(parents=True, exist_ok=True)
    
    # Check how many already exist
    existing = sum(1 for e in episodes if (podcast.audio_dir / sanitize_filename(e['title'], e.get('episode_number'))).exists())
    print(f"Already downloaded: {existing}")
    print(f"To download: {len(episodes) - existing}")

    if existing == len(episodes):
        print("All episodes already downloaded!")
        return

    # Download with progress bar
    results = {'success': 0, 'failed': 0, 'skipped': 0, 'exists': 0}
    failed_episodes = []

    print(f"\nDownloading with {DOWNLOAD_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as executor:
        futures = {
            executor.submit(download_episode, ep, podcast.audio_dir): ep
            for ep in episodes
        }
        
        with tqdm(total=len(episodes), desc="Downloading") as pbar:
            for future in as_completed(futures):
                result = future.result()
                status = result['status']
                results[status] = results.get(status, 0) + 1
                
                if status == 'failed':
                    failed_episodes.append(result)
                
                pbar.update(1)
                pbar.set_postfix({
                    'success': results['success'],
                    'failed': results['failed']
                })
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Download Summary")
    print(f"{'=' * 60}")
    print(f"  Success: {results['success']}")
    print(f"  Already existed: {results['exists']}")
    print(f"  Failed: {results['failed']}")
    print(f"  Skipped (no URL): {results['skipped']}")
    
    if failed_episodes:
        print(f"\nFailed episodes:")
        for fail in failed_episodes[:10]:
            print(f"  - EP{fail['episode']}: {fail.get('error', 'Unknown error')}")
        if len(failed_episodes) > 10:
            print(f"  ... and {len(failed_episodes) - 10} more")
    
    # Calculate total size
    total_size = sum(
        (podcast.audio_dir / sanitize_filename(e['title'], e.get('episode_number'))).stat().st_size
        for e in episodes
        if (podcast.audio_dir / sanitize_filename(e['title'], e.get('episode_number'))).exists()
    )
    print(f"\nTotal audio size: {total_size / (1024**3):.2f} GB")

    if results['failed'] > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
