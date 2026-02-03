#!/usr/bin/env python3
"""
Launch the Gooaye Pipeline UI.

This script starts the API server and opens the web UI in your browser.

Usage:
    python run_ui.py           # Start on port 8000
    python run_ui.py --port 8080  # Custom port
    python run_ui.py --no-browser # Don't auto-open browser
"""

import argparse
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


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
        print("Install with: pip install fastapi uvicorn")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Launch Gooaye Pipeline UI")
    parser.add_argument('--port', type=int, default=8000,
                        help="Port to run the server on (default: 8000)")
    parser.add_argument('--host', type=str, default="127.0.0.1",
                        help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument('--no-browser', action='store_true',
                        help="Don't automatically open browser")
    args = parser.parse_args()

    check_dependencies()

    url = f"http://{args.host}:{args.port}"

    print("=" * 50)
    print("   股癌 Pipeline Dashboard")
    print("=" * 50)
    print()
    print(f"   URL: {url}")
    print(f"   API Docs: {url}/docs")
    print()
    print("   Press Ctrl+C to stop")
    print("=" * 50)
    print()

    # Open browser after a short delay
    if not args.no_browser:
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(url)

        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    # Import and run server
    import uvicorn
    uvicorn.run(
        "server:app",
        host=args.host,
        port=args.port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
