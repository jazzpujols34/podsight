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
    python server.py              # Start on default port 8000
    python server.py --port 8080  # Start on port 8080

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

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from config import DATA_DIR, get_podcast_config, list_podcasts, DEFAULT_PODCAST

# UI directory
UI_DIR = Path(__file__).parent / "ui"
SCRIPT_DIR = Path(__file__).parent

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
    title="Podcast Transcript API",
    description="API for accessing podcast transcripts and summaries (supports multiple podcasts)",
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
    except Exception:
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

    Returns episodes that have transcripts available.
    Supports both numbered (EP*) and date-based podcasts.
    """
    episodes = []
    podcast = _current_podcast

    # Get all transcript files (both EP*.txt and other formats)
    txt_files = sorted(podcast.transcript_dir.glob("*.txt"), reverse=True)

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
}

STEP_NAMES = {
    1: "解析 RSS",
    2: "下載音訊",
    3: "語音轉錄",
    4: "AI 摘要",
    "check": "檢查新集數",
    "all": "完整 Pipeline",
}


def run_script_async(step: str | int, podcast_slug: str):
    """Run a pipeline script in background and capture output."""
    global pipeline_state

    pipeline_state["running"] = True
    pipeline_state["current_step"] = step
    pipeline_state["current_podcast"] = podcast_slug
    pipeline_state["output"] = []
    pipeline_state["started_at"] = datetime.now().isoformat()
    pipeline_state["finished_at"] = None
    pipeline_state["exit_code"] = None

    # Set environment variable for subprocess
    env = {**os.environ, 'PODCAST': podcast_slug}

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
            # Run all steps sequentially
            add_output("開始執行: 完整 Pipeline", "info")
            for s in [1, 2, 3, 4]:
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
                    env=env
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
            env=env
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


@app.post("/run/{step}")
async def run_pipeline_step(step: str, background_tasks: BackgroundTasks):
    """
    Start a pipeline step execution.

    - **step**: Step number (1-4), 'all' for full pipeline, or 'check' for new episode check
    """
    global pipeline_state

    if pipeline_state["running"]:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline 正在執行中: {STEP_NAMES.get(pipeline_state['current_step'], pipeline_state['current_step'])}"
        )

    # Validate step
    if step not in ["all", "check", "1", "2", "3", "4"]:
        raise HTTPException(status_code=400, detail=f"Invalid step: {step}")

    # Convert to int if numeric
    step_key = int(step) if step.isdigit() else step

    # Start execution in background with current podcast
    thread = threading.Thread(target=run_script_async, args=(step_key, _current_podcast.slug))
    thread.daemon = True
    thread.start()

    return {
        "status": "started",
        "step": step_key,
        "name": STEP_NAMES.get(step_key, str(step_key)),
        "podcast": _current_podcast.slug
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


@app.post("/run/stop")
async def stop_pipeline():
    """Stop the currently running pipeline."""
    global pipeline_state

    if not pipeline_state["running"]:
        raise HTTPException(status_code=400, detail="No pipeline is running")

    if pipeline_state["process"]:
        pipeline_state["process"].terminate()
        pipeline_state["output"].append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": "warning",
            "text": "Pipeline 已被使用者停止"
        })

    pipeline_state["running"] = False
    return {"status": "stopped"}


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
