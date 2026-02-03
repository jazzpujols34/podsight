#!/usr/bin/env python3
"""
Simple HTTP API server for Gooaye transcript database.

Endpoints:
    GET /                     - Serves the web UI
    GET /episode/{ep_number}  - Returns transcript + summary as JSON
    GET /latest               - Returns the most recent episode number and summary
    GET /search?q={query}     - Returns search results as JSON

Usage:
    python server.py              # Start on default port 8000
    python server.py --port 8080  # Start on port 8080

Requirements:
    pip install fastapi uvicorn
"""

import argparse
import json
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import DATA_DIR, TRANSCRIPT_DIR, EPISODES_FILE

# UI directory
UI_DIR = Path(__file__).parent / "ui"

SUMMARY_DIR = DATA_DIR / "summaries"

app = FastAPI(
    title="Gooaye Transcript API",
    description="API for accessing 股癌 podcast transcripts and summaries",
    version="1.0.0"
)

# Enable CORS for external integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

class EpisodeResponse(BaseModel):
    episode_number: int
    title: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    has_transcript: bool = False
    has_summary: bool = False


class LatestResponse(BaseModel):
    episode_number: int
    title: Optional[str] = None
    summary: Optional[str] = None
    published: Optional[str] = None


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

def get_episode_metadata(ep_number: int) -> dict | None:
    """Get episode metadata from episodes.json."""
    if not EPISODES_FILE.exists():
        return None

    try:
        with open(EPISODES_FILE, 'r', encoding='utf-8') as f:
            episodes = json.load(f)

        for ep in episodes:
            if ep.get('episode_number') == ep_number:
                return ep
        return None
    except Exception:
        return None


def get_latest_episode_number() -> int | None:
    """Get the highest episode number from transcripts."""
    max_ep = None

    for txt_file in TRANSCRIPT_DIR.glob("EP*.txt"):
        match = re.search(r'EP(\d+)', txt_file.name)
        if match:
            ep_num = int(match.group(1))
            if max_ep is None or ep_num > max_ep:
                max_ep = ep_num

    return max_ep


def get_transcript(ep_number: int) -> str | None:
    """Read transcript file for an episode."""
    transcript_file = TRANSCRIPT_DIR / f"EP{ep_number:04d}.txt"
    if transcript_file.exists():
        return transcript_file.read_text(encoding='utf-8')
    return None


def get_summary(ep_number: int) -> str | None:
    """Read summary file for an episode."""
    summary_file = SUMMARY_DIR / f"EP{ep_number:04d}_summary.txt"
    if summary_file.exists():
        return summary_file.read_text(encoding='utf-8')
    return None


def search_transcripts(
    query: str,
    limit: int = 20,
    search_summaries: bool = False
) -> list[SearchResultItem]:
    """Search transcripts or summaries for a query string."""
    results = []

    if search_summaries:
        search_dir = SUMMARY_DIR
        pattern = "EP*_summary.txt"
        source = "summary"
    else:
        search_dir = TRANSCRIPT_DIR
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
        except Exception:
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
    """Serve the web UI."""
    index_file = UI_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

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


@app.get("/api")
async def api_info():
    """API info - shows available endpoints."""
    return {
        "name": "Gooaye Transcript API",
        "version": "1.0.0",
        "endpoints": {
            "/episode/{ep_number}": "Get transcript and summary for an episode",
            "/latest": "Get the most recent episode",
            "/search?q={query}": "Search transcripts",
            "/episodes": "List all episodes",
        }
    }


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


@app.get("/latest", response_model=LatestResponse)
async def get_latest():
    """
    Get the most recent episode number and its summary.
    """
    ep_number = get_latest_episode_number()

    if ep_number is None:
        raise HTTPException(
            status_code=404,
            detail="No episodes found"
        )

    metadata = get_episode_metadata(ep_number)
    summary = get_summary(ep_number)

    return LatestResponse(
        episode_number=ep_number,
        title=metadata.get('title') if metadata else None,
        summary=summary,
        published=metadata.get('published') if metadata else None
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


@app.get("/episodes")
async def list_episodes(
    limit: int = Query(50, ge=1, le=500, description="Maximum episodes to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination")
):
    """
    List all available episodes.

    Returns episode numbers that have transcripts available.
    """
    episodes = []

    for txt_file in sorted(TRANSCRIPT_DIR.glob("EP*.txt"), reverse=True):
        match = re.search(r'EP(\d+)', txt_file.name)
        if match:
            ep_num = int(match.group(1))
            summary_file = SUMMARY_DIR / f"EP{ep_num:04d}_summary.txt"

            episodes.append({
                "episode_number": ep_num,
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


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description="Gooaye Transcript API Server")
    parser.add_argument('--port', type=int, default=8000,
                        help="Port to run the server on (default: 8000)")
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
