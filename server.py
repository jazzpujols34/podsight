#!/usr/bin/env python3
"""
HTTP API server for podcast transcript database.
Supports multiple podcasts via podcasts.yaml configuration.

Endpoints:
    GET /                           - Serves the web UI
    GET /podcasts                   - List available podcasts
    GET /episode/{ep_number}        - Returns transcript + summary as JSON
    GET /latest                     - Returns the most recent episode number and summary
    GET /search?q={query}           - Returns search results as JSON
    POST /run/{step}                - Execute a pipeline step
    GET /run/status                 - Get current execution status

Usage:
    python server.py              # Start on default port 3500
    python server.py --port 8080  # Start on custom port

Requirements:
    pip install fastapi uvicorn pyyaml python-dotenv
"""

# Load .env file first (for API keys)
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import DATA_DIR, get_podcast_config, list_podcasts, DEFAULT_PODCAST

# UI directory
UI_DIR = Path(__file__).parent / "ui"
SCRIPT_DIR = Path(__file__).parent / "scripts"

# Global state for pipeline execution
pipeline_state = {
    "running": False,
    "current_step": None,
    "current_podcast": None,
    "output": [],
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "process": None
}

# Current podcast context (default)
_current_podcast = get_podcast_config()

app = FastAPI(
    title="PodSight 聲見 API",
    description="聽見弦外之音，看見核心觀點 - Multi-podcast transcription and AI summarization",
    version="2.0.0"
)

# Enable CORS for external integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (logo, images, etc.)
app.mount("/assets", StaticFiles(directory=UI_DIR / "assets"), name="assets")

# Serve static files for PWA (icons)
STATIC_DIR = UI_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- Pydantic Models ---

class EpisodeResponse(BaseModel):
    episode_number: int
    title: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    has_transcript: bool = False
    has_summary: bool = False


class LatestResponse(BaseModel):
    episode_number: Optional[int] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    published: Optional[str] = None
    filename: Optional[str] = None  # For date-based podcasts


class SearchResultItem(BaseModel):
    episode: int
    timestamp: str
    line: int
    text: str
    source: str  # "transcript" or "summary"


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchResultItem]


# --- Helper Functions ---

def get_podcast(podcast_slug: Optional[str] = None):
    """Get podcast config, using current context if not specified."""
    global _current_podcast
    if podcast_slug:
        return get_podcast_config(podcast_slug)
    return _current_podcast


def get_episode_metadata(ep_number: int, podcast_slug: Optional[str] = None) -> dict | None:
    """Get episode metadata from episodes.json."""
    podcast = get_podcast(podcast_slug)
    if not podcast.episodes_file.exists():
        return None

    try:
        with open(podcast.episodes_file, 'r', encoding='utf-8') as f:
            episodes = json.load(f)

        for ep in episodes:
            if ep.get('episode_number') == ep_number:
                return ep
        return None
    except Exception as e:
        print(f"[WARNING] Failed to read episode metadata: {e}", file=sys.stderr)
        return None


def get_latest_episode_number(podcast_slug: Optional[str] = None) -> int | None:
    """Get the highest episode number from transcripts."""
    podcast = get_podcast(podcast_slug)
    max_ep = None

    for txt_file in podcast.transcript_dir.glob("EP*.txt"):
        match = re.search(r'EP(\d+)', txt_file.name)
        if match:
            ep_num = int(match.group(1))
            if max_ep is None or ep_num > max_ep:
                max_ep = ep_num

    return max_ep


def get_latest_episode_info(podcast_slug: Optional[str] = None) -> dict | None:
    """Get info about the latest episode (works for both numbered and date-based)."""
    podcast = get_podcast(podcast_slug)

    # First try numbered episodes
    max_ep = get_latest_episode_number(podcast_slug)
    if max_ep is not None:
        return {"episode_number": max_ep, "filename": None}

    # Fall back to date-based (get most recent by filename)
    txt_files = list(podcast.transcript_dir.glob("*.txt"))
    if not txt_files:
        return None

    # Sort by filename descending (date-based names sort chronologically)
    latest_file = sorted(txt_files, key=lambda f: f.name, reverse=True)[0]
    return {"episode_number": None, "filename": latest_file.name, "title": latest_file.stem}


def get_transcript(ep_number: int, podcast_slug: Optional[str] = None) -> str | None:
    """Read transcript file for an episode."""
    podcast = get_podcast(podcast_slug)
    transcript_file = podcast.transcript_dir / f"EP{ep_number:04d}.txt"
    if transcript_file.exists():
        return transcript_file.read_text(encoding='utf-8')
    return None


def get_summary(ep_number: int, podcast_slug: Optional[str] = None) -> str | None:
    """Read summary file for an episode."""
    podcast = get_podcast(podcast_slug)
    summary_file = podcast.summary_dir / f"EP{ep_number:04d}_summary.txt"
    if summary_file.exists():
        return summary_file.read_text(encoding='utf-8')
    return None


def search_transcripts(
    query: str,
    limit: int = 20,
    search_summaries: bool = False,
    podcast_slug: Optional[str] = None
) -> list[SearchResultItem]:
    """Search transcripts or summaries for a query string."""
    podcast = get_podcast(podcast_slug)
    results = []

    if search_summaries:
        search_dir = podcast.summary_dir
        pattern = "EP*_summary.txt"
        source = "summary"
    else:
        search_dir = podcast.transcript_dir
        pattern = "EP*.txt"
        source = "transcript"

    if not search_dir.exists():
        return results

    query_lower = query.lower()

    for file_path in sorted(search_dir.glob(pattern)):
        match = re.search(r'EP(\d+)', file_path.name)
        if not match:
            continue
        ep_num = int(match.group(1))

        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"[WARNING] Failed to read {file_path}: {e}", file=sys.stderr)
            continue

        for line_num, line in enumerate(content.split('\n'), 1):
            if query_lower in line.lower():
                # Extract timestamp if present
                ts_match = re.match(r'\[(\d+:\d+)\]', line)
                timestamp = ts_match.group(1) if ts_match else ""

                results.append(SearchResultItem(
                    episode=ep_num,
                    timestamp=timestamp,
                    line=line_num,
                    text=line.strip(),
                    source=source
                ))

                if len(results) >= limit:
                    return results

    return results


# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web UI with no-cache headers."""
    from fastapi.responses import Response
    index_file = UI_DIR / "index.html"
    if index_file.exists():
        content = index_file.read_text()
        return Response(
            content=content,
            media_type="text/html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )

    # Fallback to API info if UI not found
    return HTMLResponse(content="""
    <html>
        <head><title>Gooaye API</title></head>
        <body style="font-family: sans-serif; padding: 2rem;">
            <h1>Gooaye Transcript API</h1>
            <p>UI not found. Available endpoints:</p>
            <ul>
                <li><a href="/api">/api</a> - API info</li>
                <li><a href="/docs">/docs</a> - API documentation</li>
                <li><a href="/episodes">/episodes</a> - List episodes</li>
            </ul>
        </body>
    </html>
    """)


@app.get("/manifest.json")
async def manifest():
    """Serve PWA manifest file."""
    manifest_file = UI_DIR / "manifest.json"
    if manifest_file.exists():
        return FileResponse(manifest_file, media_type="application/manifest+json")
    return {"error": "manifest not found"}


@app.get("/sw.js")
async def service_worker():
    """Serve PWA service worker."""
    sw_file = UI_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(sw_file, media_type="application/javascript")
    return {"error": "service worker not found"}


@app.get("/api")
async def api_info():
    """API info - shows available endpoints."""
    return {
        "name": "Podcast Transcript API",
        "version": "2.0.0",
        "current_podcast": _current_podcast.name,
        "endpoints": {
            "/podcasts": "List available podcasts",
            "/podcasts/{slug}/select": "Switch to a different podcast",
            "/episode/{ep_number}": "Get transcript and summary for an episode",
            "/latest": "Get the most recent episode",
            "/search?q={query}": "Search transcripts",
            "/episodes": "List all episodes",
        }
    }


@app.get("/podcasts")
async def get_podcasts():
    """List all available podcasts."""
    podcasts = []
    for slug, name in list_podcasts().items():
        podcast = get_podcast_config(slug)
        # Count episodes
        transcript_count = len(list(podcast.transcript_dir.glob("*.txt")))
        podcasts.append({
            "slug": slug,
            "name": name,
            "is_current": slug == _current_podcast.slug,
            "transcript_count": transcript_count,
            "data_dir": str(podcast.data_dir)
        })
    return {"podcasts": podcasts, "current": _current_podcast.slug}


@app.post("/podcasts/{slug}/select")
async def select_podcast(slug: str):
    """Switch to a different podcast."""
    global _current_podcast
    try:
        _current_podcast = get_podcast_config(slug)
        return {"status": "ok", "current": _current_podcast.slug, "name": _current_podcast.name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/episode/{ep_number}", response_model=EpisodeResponse)
async def get_episode(ep_number: int):
    """
    Get transcript and summary for a specific episode.

    - **ep_number**: Episode number (e.g., 621)
    """
    transcript = get_transcript(ep_number)
    summary = get_summary(ep_number)

    if transcript is None and summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Episode {ep_number} not found"
        )

    metadata = get_episode_metadata(ep_number)
    title = metadata.get('title') if metadata else None

    return EpisodeResponse(
        episode_number=ep_number,
        title=title,
        transcript=transcript,
        summary=summary,
        has_transcript=transcript is not None,
        has_summary=summary is not None
    )


@app.get("/episode/file/{filename:path}")
async def get_episode_by_file(filename: str):
    """
    Get transcript and summary by filename (for non-numbered podcasts).

    - **filename**: Transcript filename (e.g., "2026_1_14_三_展示走向工廠.txt")
    """
    podcast = _current_podcast

    # Remove .txt extension if present
    stem = filename[:-4] if filename.endswith('.txt') else filename

    transcript_file = podcast.transcript_dir / f"{stem}.txt"
    summary_file = podcast.summary_dir / f"{stem}_summary.txt"

    transcript = transcript_file.read_text(encoding='utf-8') if transcript_file.exists() else None
    summary = summary_file.read_text(encoding='utf-8') if summary_file.exists() else None

    if transcript is None and summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"Episode '{filename}' not found"
        )

    return {
        "episode_number": None,
        "title": stem[:50],
        "filename": filename,
        "transcript": transcript,
        "summary": summary,
        "has_transcript": transcript is not None,
        "has_summary": summary is not None
    }


class SaveSummaryRequest(BaseModel):
    summary: str


@app.put("/episode/{ep_number}/summary")
async def save_episode_summary(ep_number: int, request: SaveSummaryRequest):
    """
    Save/update summary for a numbered episode.
    """
    podcast = _current_podcast
    summary_file = podcast.summary_dir / f"EP{ep_number:04d}_summary.txt"

    try:
        summary_file.write_text(request.summary, encoding='utf-8')
        return {"status": "ok", "message": f"Summary saved for EP{ep_number}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/episode/file/{filename:path}/summary")
async def save_file_summary(filename: str, request: SaveSummaryRequest):
    """
    Save/update summary for a file-based episode.
    """
    podcast = _current_podcast

    # Remove .txt extension if present
    stem = filename[:-4] if filename.endswith('.txt') else filename
    summary_file = podcast.summary_dir / f"{stem}_summary.txt"

    try:
        summary_file.write_text(request.summary, encoding='utf-8')
        return {"status": "ok", "message": f"Summary saved for {stem}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Custom Prompt Endpoints ---

class CustomPromptRequest(BaseModel):
    prompt: str


@app.get("/settings/prompt")
async def get_custom_prompt():
    """Get the custom summary prompt for the current podcast."""
    podcast = _current_podcast
    prompt_file = podcast.data_dir / "custom_prompt.txt"

    if prompt_file.exists():
        return {"prompt": prompt_file.read_text(encoding='utf-8'), "is_custom": True}

    # Return default prompt
    default_prompt = f'''Summarize this "{podcast.name}" podcast episode in Traditional Chinese.

Host: {podcast.host}

Include:
- 一句話總結
- 主要討論話題 (bullet points, 詳細說明每個話題)
- 提到的股票/ETF/標的
- {podcast.host} 的觀點或金句

Aim for 400-500 words. Be detailed but concise.

Transcript:
{{transcript}}'''

    return {"prompt": default_prompt, "is_custom": False}


@app.put("/settings/prompt")
async def save_custom_prompt(request: CustomPromptRequest):
    """Save a custom summary prompt for the current podcast."""
    podcast = _current_podcast
    prompt_file = podcast.data_dir / "custom_prompt.txt"

    try:
        prompt_file.write_text(request.prompt, encoding='utf-8')
        return {"status": "ok", "message": "Custom prompt saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/settings/prompt")
async def delete_custom_prompt():
    """Delete custom prompt and revert to default."""
    podcast = _current_podcast
    prompt_file = podcast.data_dir / "custom_prompt.txt"

    if prompt_file.exists():
        prompt_file.unlink()

    return {"status": "ok", "message": "Reverted to default prompt"}


# --- Social Push Endpoints ---

from social.draft import DraftManager, SocialDraft
from social.publishers import TwitterPublisher, ThreadsPublisher, LinePublisher, InstagramPublisher, TelegramPublisher


@app.get("/social/drafts")
async def list_social_drafts(status: Optional[str] = None):
    """List all social drafts, optionally filtered by status."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    drafts = draft_manager.list_drafts(status)
    return {
        "drafts": [d.to_dict() for d in drafts],
        "count": len(drafts),
        "podcast": _current_podcast.slug
    }


@app.get("/social/drafts/{episode_id}")
async def get_social_draft(episode_id: str):
    """Get draft for a specific episode."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    draft = draft_manager.get_draft(episode_id)

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Include platform content
    result = draft.to_dict()
    result["content"] = {}

    for platform in ["twitter", "threads", "line", "instagram"]:
        content = draft_manager.get_platform_content(episode_id, platform)
        if content:
            result["content"][platform] = content

    return result


@app.put("/social/drafts/{episode_id}/{platform}")
async def update_social_draft(episode_id: str, platform: str, request: Request):
    """Update platform-specific content for a draft."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    draft = draft_manager.get_draft(episode_id)

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if platform not in ["twitter", "threads", "line", "instagram", "telegram"]:
        raise HTTPException(status_code=400, detail="Invalid platform")

    content = await request.json()
    draft_manager.save_platform_content(episode_id, platform, content)

    return {"status": "ok", "message": f"Updated {platform} content"}


@app.post("/social/drafts/{episode_id}/{platform}/publish")
async def publish_social_draft(episode_id: str, platform: str):
    """Publish draft to a specific platform."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    draft = draft_manager.get_draft(episode_id)

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if platform not in ["twitter", "threads", "line", "instagram", "telegram"]:
        raise HTTPException(status_code=400, detail="Invalid platform")

    # Get content
    content = draft_manager.get_platform_content(episode_id, platform)
    if not content:
        raise HTTPException(status_code=400, detail="No content for platform")

    # Get publisher
    publishers = {
        "twitter": TwitterPublisher,
        "threads": ThreadsPublisher,
        "line": LinePublisher,
        "instagram": InstagramPublisher,
        "telegram": TelegramPublisher,
    }

    publisher = publishers[platform]()

    if not publisher.is_configured():
        raise HTTPException(
            status_code=400,
            detail=f"{platform} not configured. Check environment variables."
        )

    # Get image path for Instagram
    image_path = None
    if platform == "instagram":
        image_file = draft.platforms[platform].image_file
        if image_file:
            image_path = draft_manager.get_draft_dir(episode_id) / image_file

    # Publish
    result = publisher.publish(content, image_path)

    # Update draft status
    draft.platforms[platform].status = "published" if result.success else "failed"
    draft.platforms[platform].published_at = result.published_at.isoformat() if result.published_at else None
    draft.platforms[platform].post_ids = result.post_ids
    draft.platforms[platform].error = result.error
    draft.platforms[platform].url = result.url
    draft.update_status()
    draft_manager.save_draft(draft)

    if result.success:
        return {
            "status": "ok",
            "platform": platform,
            "post_ids": result.post_ids,
            "url": result.url
        }
    else:
        raise HTTPException(status_code=500, detail=result.error)


@app.post("/social/drafts/{episode_id}/publish-all")
async def publish_all_platforms(episode_id: str):
    """Publish draft to all configured platforms."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    draft = draft_manager.get_draft(episode_id)

    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    results = {}
    publishers = {
        "twitter": TwitterPublisher,
        "threads": ThreadsPublisher,
        "line": LinePublisher,
        "instagram": InstagramPublisher,
        "telegram": TelegramPublisher,
    }

    for platform, PublisherClass in publishers.items():
        publisher = PublisherClass()

        if not publisher.is_configured():
            results[platform] = {"success": False, "error": "Not configured"}
            continue

        content = draft_manager.get_platform_content(episode_id, platform)
        if not content:
            results[platform] = {"success": False, "error": "No content"}
            continue

        image_path = None
        if platform == "instagram":
            image_file = draft.platforms[platform].image_file
            if image_file:
                image_path = draft_manager.get_draft_dir(episode_id) / image_file

        result = publisher.publish(content, image_path)
        results[platform] = {
            "success": result.success,
            "post_ids": result.post_ids,
            "url": result.url,
            "error": result.error
        }

        # Update draft
        draft.platforms[platform].status = "published" if result.success else "failed"
        draft.platforms[platform].published_at = result.published_at.isoformat() if result.published_at else None
        draft.platforms[platform].post_ids = result.post_ids
        draft.platforms[platform].error = result.error

    draft.update_status()
    draft_manager.save_draft(draft)

    return {"status": "ok", "results": results}


@app.delete("/social/drafts/{episode_id}")
async def delete_social_draft(episode_id: str):
    """Delete a draft and all its files."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    draft_manager.delete_draft(episode_id)
    return {"status": "ok", "message": f"Deleted draft for {episode_id}"}


@app.post("/social/drafts/{episode_id}/regenerate")
async def regenerate_social_draft(episode_id: str):
    """Regenerate drafts from the summary file."""
    import subprocess
    import sys

    # Run the generate script for this episode
    ep_num = episode_id.replace("EP", "")
    result = subprocess.run(
        [sys.executable, "scripts/05_generate_social.py", "--ep", ep_num, "--regenerate"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent),
        env={**os.environ, "PODCAST": _current_podcast.slug}
    )

    if result.returncode == 0:
        return {"status": "ok", "message": f"Regenerated drafts for {episode_id}"}
    else:
        raise HTTPException(status_code=500, detail=result.stderr)


@app.get("/social/image/{episode_id}")
async def get_social_image(episode_id: str):
    """Get the Instagram card image for an episode."""
    draft_manager = DraftManager(_current_podcast.data_dir)
    image_path = draft_manager.get_draft_dir(episode_id) / "instagram_card.png"

    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path, media_type="image/png")


@app.get("/social/config")
async def get_social_config():
    """Get social configuration (which platforms are configured)."""
    publishers = {
        "twitter": TwitterPublisher(),
        "threads": ThreadsPublisher(),
        "line": LinePublisher(),
        "instagram": InstagramPublisher(),
        "telegram": TelegramPublisher(),
    }

    return {
        "platforms": {
            name: {
                "configured": pub.is_configured(),
                "platform": pub.platform
            }
            for name, pub in publishers.items()
        }
    }


@app.get("/latest", response_model=LatestResponse)
async def get_latest():
    """
    Get the most recent episode number and its summary.
    """
    latest_info = get_latest_episode_info()

    if latest_info is None:
        raise HTTPException(
            status_code=404,
            detail="No episodes found"
        )

    ep_number = latest_info.get("episode_number")
    filename = latest_info.get("filename")

    if ep_number is not None:
        # Numbered episode
        metadata = get_episode_metadata(ep_number)
        summary = get_summary(ep_number)
        return LatestResponse(
            episode_number=ep_number,
            title=metadata.get('title') if metadata else None,
            summary=summary,
            published=metadata.get('published') if metadata else None
        )
    else:
        # Date-based episode
        podcast = get_podcast()
        title = latest_info.get("title", filename)
        summary_file = podcast.summary_dir / f"{Path(filename).stem}_summary.txt"
        summary = summary_file.read_text(encoding='utf-8') if summary_file.exists() else None
        return LatestResponse(
            episode_number=None,
            title=title,
            summary=summary,
            filename=filename
        )


@app.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    summary: bool = Query(False, description="Search summaries instead of transcripts")
):
    """
    Search transcripts or summaries for a query string.

    - **q**: Search query (required)
    - **limit**: Maximum number of results (default: 20, max: 100)
    - **summary**: If true, search summaries instead of transcripts
    """
    results = search_transcripts(q, limit=limit, search_summaries=summary)

    return SearchResponse(
        query=q,
        count=len(results),
        results=results
    )


def get_episode_sort_key(filename: str) -> tuple:
    """Get sort key for episode filename (handles both EP* and date-based)."""
    # For numbered episodes: EP0634.txt -> (1, 634)
    ep_match = re.search(r'EP(\d+)', filename)
    if ep_match:
        return (1, int(ep_match.group(1)))

    # For date-based: 2026_2_11_... -> (0, 20260211)
    date_match = re.match(r'(\d{4})_(\d{1,2})_(\d{1,2})_', filename)
    if date_match:
        year, month, day = date_match.groups()
        date_num = int(year) * 10000 + int(month) * 100 + int(day)
        return (0, date_num)

    # Fallback: sort by filename
    return (2, filename)


@app.get("/audio/{filename:path}")
async def get_audio_file(filename: str):
    """Serve audio file for playback."""
    podcast = _current_podcast

    # Try to find the audio file
    audio_file = podcast.audio_dir / filename
    if not audio_file.exists():
        # Try with .mp3 extension
        audio_file = podcast.audio_dir / f"{filename}.mp3"

    if not audio_file.exists():
        raise HTTPException(status_code=404, detail=f"Audio file not found: {filename}")

    return FileResponse(
        audio_file,
        media_type="audio/mpeg",
        filename=audio_file.name
    )


@app.get("/episodes")
async def list_episodes(
    limit: int = Query(50, ge=1, le=500, description="Maximum episodes to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    List all available episodes.

    Returns episodes that have transcripts available.
    Supports both numbered (EP*) and date-based podcasts.
    """
    episodes = []
    podcast = _current_podcast

    # Get all transcript files and sort properly (date-based or EP number)
    txt_files = sorted(
        podcast.transcript_dir.glob("*.txt"),
        key=lambda f: get_episode_sort_key(f.name),
        reverse=True
    )

    for txt_file in txt_files:
        # Skip JSON files
        if txt_file.suffix != '.txt':
            continue

        # Try to extract episode number for numbered podcasts
        match = re.search(r'EP(\d+)', txt_file.name)
        if match:
            ep_num = int(match.group(1))
            summary_file = podcast.summary_dir / f"EP{ep_num:04d}_summary.txt"
            episodes.append({
                "episode_number": ep_num,
                "title": txt_file.stem,
                "filename": txt_file.name,
                "has_transcript": True,
                "has_summary": summary_file.exists()
            })
        else:
            # For non-numbered podcasts, use filename as identifier
            summary_file = podcast.summary_dir / f"{txt_file.stem}_summary.txt"
            episodes.append({
                "episode_number": None,
                "title": txt_file.stem[:50],  # Truncate long names
                "filename": txt_file.name,
                "has_transcript": True,
                "has_summary": summary_file.exists()
            })

    # Apply pagination
    paginated = episodes[offset:offset + limit]

    return {
        "total": len(episodes),
        "offset": offset,
        "limit": limit,
        "episodes": paginated
    }


# --- Pipeline Execution Endpoints ---

STEP_SCRIPTS = {
    1: "01_parse_rss.py",
    2: "02_download_audio.py",
    3: "03_transcribe.py",
    4: "04_summarize.py",
    5: "05_generate_social.py",
}

STEP_NAMES = {
    1: "解析 RSS",
    2: "下載音訊",
    3: "語音轉錄",
    4: "AI 摘要",
    5: "社群草稿",
    "check": "檢查新集數",
    "all": "完整 Pipeline",
}


def run_script_async(step: str | int, podcast_slug: str, providers: dict = None):
    """Run a pipeline script in background and capture output."""
    global pipeline_state

    providers = providers or {"transcribe": "groq", "summary": "gemini"}

    pipeline_state["running"] = True
    pipeline_state["current_step"] = step
    pipeline_state["current_podcast"] = podcast_slug
    pipeline_state["output"] = []
    pipeline_state["started_at"] = datetime.now().isoformat()
    pipeline_state["finished_at"] = None
    pipeline_state["exit_code"] = None

    # Set environment variables for subprocess
    env = {
        **os.environ,
        'PODCAST': podcast_slug,
        'WHISPER_PROVIDER': providers.get("transcribe", "groq"),
        'SUMMARY_PROVIDER': providers.get("summary", "gemini")
    }

    def add_output(line: str, level: str = "info"):
        pipeline_state["output"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level,
            "text": line
        })
        # Keep only last 500 lines
        if len(pipeline_state["output"]) > 500:
            pipeline_state["output"] = pipeline_state["output"][-500:]

    podcast_name = get_podcast_config(podcast_slug).name
    add_output(f"Podcast: {podcast_name}", "info")

    try:
        # Determine which script to run
        if step == "check":
            script = SCRIPT_DIR / "auto_check_new_episodes.py"
            add_output(f"開始執行: 檢查新集數", "info")
        elif step == "all":
            # Run all steps sequentially (including social draft generation)
            add_output("開始執行: 完整 Pipeline", "info")
            for s in [1, 2, 3, 4, 5]:
                if not pipeline_state["running"]:
                    break
                script = SCRIPT_DIR / STEP_SCRIPTS[s]
                add_output(f"\n{'='*40}", "info")
                add_output(f"Step {s}: {STEP_NAMES[s]}", "info")
                add_output(f"{'='*40}", "info")

                process = subprocess.Popen(
                    [sys.executable, str(script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    cwd=str(SCRIPT_DIR),
                    env=env,
                    start_new_session=True  # Enable process group for clean kill
                )
                pipeline_state["process"] = process

                for line in process.stdout:
                    add_output(line.rstrip())

                process.wait()
                if process.returncode != 0:
                    add_output(f"Step {s} 失敗 (exit code: {process.returncode})", "error")
                    pipeline_state["exit_code"] = process.returncode
                    break
                else:
                    add_output(f"Step {s} 完成!", "success")

            pipeline_state["finished_at"] = datetime.now().isoformat()
            pipeline_state["running"] = False
            if pipeline_state["exit_code"] is None:
                pipeline_state["exit_code"] = 0
                add_output("\n完整 Pipeline 執行完成!", "success")
            return

        else:
            script = SCRIPT_DIR / STEP_SCRIPTS[int(step)]
            add_output(f"開始執行: Step {step} - {STEP_NAMES[int(step)]}", "info")

        # Run single script
        process = subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(SCRIPT_DIR),
            env=env,
            start_new_session=True  # Enable process group for clean kill
        )
        pipeline_state["process"] = process

        for line in process.stdout:
            add_output(line.rstrip())

        process.wait()
        pipeline_state["exit_code"] = process.returncode

        if process.returncode == 0:
            add_output("\n執行完成!", "success")
        else:
            add_output(f"\n執行失敗 (exit code: {process.returncode})", "error")

    except Exception as e:
        add_output(f"錯誤: {str(e)}", "error")
        pipeline_state["exit_code"] = -1

    finally:
        pipeline_state["finished_at"] = datetime.now().isoformat()
        pipeline_state["running"] = False
        pipeline_state["process"] = None


@app.post("/run/stop")
async def stop_pipeline():
    """Stop the currently running pipeline."""
    global pipeline_state

    if not pipeline_state["running"]:
        raise HTTPException(status_code=400, detail="No pipeline is running")

    if pipeline_state["process"]:
        import signal
        try:
            # Try graceful termination first
            pipeline_state["process"].terminate()
            try:
                pipeline_state["process"].wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop
                pipeline_state["process"].kill()
                # Also kill any child processes
                try:
                    os.killpg(os.getpgid(pipeline_state["process"].pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        except Exception as e:
            pass  # Process may have already exited

        pipeline_state["output"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "warning",
            "text": "Pipeline 已被使用者停止"
        })

    pipeline_state["running"] = False
    pipeline_state["finished_at"] = datetime.now().isoformat()
    pipeline_state["exit_code"] = -1
    return {"status": "stopped"}


@app.post("/run/{step}")
async def run_pipeline_step(
    step: str,
    background_tasks: BackgroundTasks,
    transcribe_provider: str = Query(default="groq", description="Transcription provider: groq, openai, local"),
    summary_provider: str = Query(default="gemini", description="Summary provider: gemini, anthropic, openai")
):
    """
    Start a pipeline step execution.

    - **step**: Step number (1-5), 'all' for full pipeline, or 'check' for new episode check
    - **transcribe_provider**: Provider for transcription (groq, openai, local)
    - **summary_provider**: Provider for summarization (gemini, anthropic, openai)
    """
    global pipeline_state

    if pipeline_state["running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline 正在執行中: {STEP_NAMES.get(pipeline_state['current_step'], pipeline_state['current_step'])}"
        )

    # Validate step
    if step not in ["all", "check", "1", "2", "3", "4", "5"]:
        raise HTTPException(status_code=400, detail=f"Invalid step: {step}")

    # Convert to int if numeric
    step_key = int(step) if step.isdigit() else step

    # Provider options
    providers = {
        "transcribe": transcribe_provider,
        "summary": summary_provider
    }

    # Start execution in background with current podcast
    thread = threading.Thread(target=run_script_async, args=(step_key, _current_podcast.slug, providers))
    thread.daemon = True
    thread.start()

    return {
        "status": "started",
        "step": step_key,
        "name": STEP_NAMES.get(step_key, str(step_key)),
        "podcast": _current_podcast.slug,
        "providers": providers
    }


@app.get("/run/status")
async def get_pipeline_status():
    """Get current pipeline execution status and output."""
    return {
        "running": pipeline_state["running"],
        "current_step": pipeline_state["current_step"],
        "step_name": STEP_NAMES.get(pipeline_state["current_step"], str(pipeline_state["current_step"])) if pipeline_state["current_step"] else None,
        "current_podcast": pipeline_state["current_podcast"],
        "started_at": pipeline_state["started_at"],
        "finished_at": pipeline_state["finished_at"],
        "exit_code": pipeline_state["exit_code"],
        "output": pipeline_state["output"],
        "output_count": len(pipeline_state["output"])
    }


@app.get("/stats/cost")
async def get_cost_estimate():
    """
    Get estimated API cost breakdown for the current podcast.

    Estimates based on:
    - OpenAI Whisper: $0.006/minute (avg ~25 min/episode)
    - Claude Sonnet: ~$0.003/1K input + $0.015/1K output tokens
    - GPT-4o: ~$0.005/1K input + $0.015/1K output tokens
    - Gemini: Free
    - Groq: Free (rate limited)
    """
    podcast = _current_podcast

    # Count audio files and estimate duration
    audio_files = list(podcast.audio_dir.glob("*.mp3"))
    audio_count = len(audio_files)

    # Estimate audio duration from file sizes (bitrate ~128kbps for podcasts)
    total_audio_mb = sum(f.stat().st_size / (1024 * 1024) for f in audio_files)
    # 128kbps = 16KB/s, so MB / 0.96 ≈ minutes
    estimated_minutes = total_audio_mb / 0.96

    # Count transcripts and summaries
    transcript_files = list(podcast.transcript_dir.glob("*.txt"))
    summary_files = list(podcast.summary_dir.glob("*_summary.txt"))
    transcript_count = len(transcript_files)
    summary_count = len(summary_files)

    # Estimate transcript character counts (for summary input estimation)
    total_transcript_chars = sum(
        f.stat().st_size for f in transcript_files
    )
    # Approximate tokens: 1 Chinese char ≈ 1.5 tokens, 1 English word ≈ 1.3 tokens
    # Mixed content: ~1 token per 2 chars
    estimated_transcript_tokens = total_transcript_chars / 2

    # Estimate summary output tokens (~500 words * 1.3 tokens ≈ 650 tokens/summary)
    estimated_summary_output_tokens = summary_count * 650

    # Calculate costs
    costs = {
        "transcription": {
            "openai_whisper": round(estimated_minutes * 0.006, 2),
            "groq": 0.0,  # Free
            "local": 0.0   # Free (local compute)
        },
        "summarization": {
            "claude": round(
                (estimated_transcript_tokens / 1000 * 0.003) +
                (estimated_summary_output_tokens / 1000 * 0.015), 2
            ),
            "openai_gpt4o": round(
                (estimated_transcript_tokens / 1000 * 0.005) +
                (estimated_summary_output_tokens / 1000 * 0.015), 2
            ),
            "gemini": 0.0  # Free
        }
    }

    return {
        "podcast": podcast.name,
        "stats": {
            "audio_files": audio_count,
            "estimated_audio_minutes": round(estimated_minutes, 1),
            "transcripts": transcript_count,
            "summaries": summary_count,
            "estimated_transcript_tokens": int(estimated_transcript_tokens)
        },
        "estimated_costs_usd": costs,
        "total_if_paid": {
            "transcription_openai": costs["transcription"]["openai_whisper"],
            "summarization_claude": costs["summarization"]["claude"],
            "summarization_openai": costs["summarization"]["openai_gpt4o"]
        },
        "note": "Groq transcription and Gemini summarization are free (with rate limits)"
    }


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Gooaye Transcript API Server")
    parser.add_argument('--port', type=int, default=3500,
                        help="Port to run the server on (default: 3500)")
    parser.add_argument('--host', type=str, default="127.0.0.1",
                        help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument('--reload', action='store_true',
                        help="Enable auto-reload for development")
    args = parser.parse_args()

    print(f"Starting Gooaye Transcript API on http://{args.host}:{args.port}")
    print(f"API docs available at http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
