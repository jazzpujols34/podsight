#!/usr/bin/env python3
"""
Step 1: Parse podcast RSS feed and extract episode metadata.

Output: data/{podcast}/episodes.json with all episode info including audio URLs

Supports multiple podcasts via PODCAST environment variable.
"""

import json
import re
import sys
from pathlib import Path
import feedparser
import ssl
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_podcast_config

# Fix SSL certificate verification issues
ssl._create_default_https_context = ssl._create_unverified_context

# Get podcast config (from env or default)
podcast = get_podcast_config()


def extract_episode_number(title: str) -> int | None:
    """Extract episode number from title using podcast's pattern."""
    return podcast.extract_episode_number(title)

def parse_duration(duration_str: str) -> int:
    """Parse duration string to seconds. Handles HH:MM:SS or MM:SS or seconds."""
    if not duration_str:
        return 0
    
    # If it's just a number (seconds)
    if duration_str.isdigit():
        return int(duration_str)
    
    parts = duration_str.split(':')
    if len(parts) == 3:  # HH:MM:SS
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    elif len(parts) == 2:  # MM:SS
        return int(parts[0]) * 60 + int(parts[1])
    return 0

def parse_rss_feed() -> list[dict]:
    """Parse the RSS feed and return episode metadata."""
    print(f"Fetching RSS feed: {podcast.rss_url}")
    feed = feedparser.parse(podcast.rss_url)
    
    if feed.bozo:
        print(f"Warning: Feed parsing had issues: {feed.bozo_exception}")
    
    print(f"Found {len(feed.entries)} entries in feed")
    print(f"Feed title: {feed.feed.get('title', 'Unknown')}")
    
    episodes = []
    for entry in feed.entries:
        # Find audio enclosure
        audio_url = None
        audio_type = None
        audio_length = None
        
        for link in entry.get('links', []):
            if link.get('type', '').startswith('audio/'):
                audio_url = link.get('href')
                audio_type = link.get('type')
                audio_length = link.get('length')
                break
        
        # Also check enclosures
        for enc in entry.get('enclosures', []):
            if enc.get('type', '').startswith('audio/'):
                audio_url = enc.get('href') or enc.get('url')
                audio_type = enc.get('type')
                audio_length = enc.get('length')
                break
        
        # Get duration from itunes extension
        duration_str = entry.get('itunes_duration', '')
        duration_seconds = parse_duration(duration_str)
        
        episode = {
            'title': entry.get('title', ''),
            'episode_number': extract_episode_number(entry.get('title', '')),
            'published': entry.get('published', ''),
            'audio_url': audio_url,
            'audio_type': audio_type,
            'audio_length': audio_length,
            'duration_str': duration_str,
            'duration_seconds': duration_seconds,
            'guid': entry.get('id', ''),
            'summary': entry.get('summary', '')[:500] if entry.get('summary') else '',
        }
        episodes.append(episode)
    
    # Sort by episode number (newest first typically, but let's sort by number)
    episodes_with_num = [e for e in episodes if e['episode_number'] is not None]
    episodes_without_num = [e for e in episodes if e['episode_number'] is None]
    
    episodes_with_num.sort(key=lambda x: x['episode_number'], reverse=True)
    
    all_episodes = episodes_with_num + episodes_without_num
    
    return all_episodes

def main():
    print("=" * 60)
    print(f"RSS Parser: {podcast.name}")
    print("=" * 60)

    episodes = parse_rss_feed()

    # Apply max_episodes limit if set (for daily podcasts)
    if podcast.max_episodes and len(episodes) > podcast.max_episodes:
        print(f"\nApplying max_episodes limit: {podcast.max_episodes}")
        episodes = episodes[:podcast.max_episodes]

    # Save to JSON
    podcast.data_dir.mkdir(parents=True, exist_ok=True)
    with open(podcast.episodes_file, 'w', encoding='utf-8') as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(episodes)} episodes to {podcast.episodes_file}")
    
    # Stats
    with_audio = sum(1 for e in episodes if e['audio_url'])
    with_number = sum(1 for e in episodes if e['episode_number'])
    total_duration = sum(e['duration_seconds'] for e in episodes)
    
    print(f"\nStats:")
    print(f"  - Episodes with audio URL: {with_audio}")
    print(f"  - Episodes with EP number: {with_number}")
    print(f"  - Total duration: {total_duration // 3600}h {(total_duration % 3600) // 60}m")
    
    # Show sample
    print(f"\nSample episodes:")
    for ep in episodes[:3]:
        print(f"  - {ep['title']}")
        print(f"    Audio: {ep['audio_url'][:80] if ep['audio_url'] else 'None'}...")
        print(f"    Duration: {ep['duration_str']}")
        print()
    
    if episodes:
        oldest = min((e for e in episodes if e['episode_number']), 
                     key=lambda x: x['episode_number'], default=None)
        if oldest:
            print(f"Oldest episode: EP{oldest['episode_number']} - {oldest['title'][:50]}...")

if __name__ == "__main__":
    main()
