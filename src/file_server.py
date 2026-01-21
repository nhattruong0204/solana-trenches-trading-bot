#!/usr/bin/env python3
"""
Simple HTTP file server for compare results.

Serves JSON files from /app/data/compare_results/
Accessible at http://<vps-ip>:8080/
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from aiohttp import web

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("/app/data/compare_results")
PORT = 8080


async def list_files(request: web.Request) -> web.Response:
    """List all available result files."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    files = []
    for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        stat = f.stat()
        files.append({
            "name": f.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"/{f.name}",
        })
    
    # Return HTML page with file listing
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Compare Results</title>
        <style>
            body { font-family: monospace; padding: 20px; background: #1a1a1a; color: #fff; }
            h1 { color: #4CAF50; }
            table { border-collapse: collapse; width: 100%; }
            th, td { padding: 10px; text-align: left; border-bottom: 1px solid #333; }
            a { color: #2196F3; text-decoration: none; }
            a:hover { text-decoration: underline; }
            .size { color: #888; }
            .date { color: #888; }
        </style>
    </head>
    <body>
        <h1>📊 Compare Results Archive</h1>
        <p>JSON files for AI analysis</p>
        <table>
            <tr><th>File</th><th>Size</th><th>Modified</th></tr>
    """
    
    for f in files:
        html += f"""
            <tr>
                <td><a href="{f['url']}">{f['name']}</a></td>
                <td class="size">{f['size']:,} bytes</td>
                <td class="date">{f['modified']}</td>
            </tr>
        """
    
    html += """
        </table>
        <hr>
        <p>💡 Tips:</p>
        <ul>
            <li><a href="/latest.json">latest.json</a> - Most recent comparison</li>
            <li><a href="/api/files">API: /api/files</a> - JSON list of files</li>
        </ul>
    </body>
    </html>
    """
    
    return web.Response(text=html, content_type="text/html")


async def api_files(request: web.Request) -> web.Response:
    """API endpoint to list files as JSON."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    files = []
    for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        stat = f.stat()
        files.append({
            "name": f.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "url": f"http://{request.host}/{f.name}",
        })
    
    return web.json_response({"files": files, "count": len(files)})


async def serve_file(request: web.Request) -> web.Response:
    """Serve a specific JSON file."""
    filename = request.match_info.get("filename", "")
    
    # Security: only allow .json files
    if not filename.endswith(".json"):
        return web.Response(status=404, text="Not found")
    
    filepath = RESULTS_DIR / filename
    
    if not filepath.exists():
        return web.Response(status=404, text=f"File not found: {filename}")
    
    # Read and return JSON
    with open(filepath, 'r') as f:
        content = f.read()
    
    return web.Response(
        text=content,
        content_type="application/json",
        headers={
            "Access-Control-Allow-Origin": "*",  # Allow CORS
        }
    )


async def create_app() -> web.Application:
    """Create the web application."""
    app = web.Application()
    
    app.router.add_get("/", list_files)
    app.router.add_get("/api/files", api_files)
    app.router.add_get("/{filename}", serve_file)
    
    return app


async def start_server():
    """Start the file server."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"📁 File server started on http://0.0.0.0:{PORT}")
    
    # Keep running
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_server())
