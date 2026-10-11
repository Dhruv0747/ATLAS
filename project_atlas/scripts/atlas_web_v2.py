"""Static file route for ATLAS Glass UI V2 (/v2/...), served by rover-status-web on the Jetson.

Additive and read-only: GET of an allow-listed file under the V2 directory, nothing else.
No directory listing, no dotfiles, no path traversal, no new endpoints. V1 pages are untouched.
The directory defaults to <project_atlas>/web/v2 and can be overridden with ATLAS_WEB_V2_DIR.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

V2_DIR = Path(os.environ.get('ATLAS_WEB_V2_DIR') or Path(__file__).resolve().parent.parent / 'web' / 'v2').resolve()
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8'}
PAGES = {'': 'index.html', 'mapping': 'mapping.html', 'commissioning': 'commissioning.html', 'wifi': 'wifi.html'}


def handles(raw_path):
    path = urlsplit(raw_path).path
    return path == '/v2' or path.startswith('/v2/')


def resolve(raw_path):
    """Return (file Path, content type) for an allowed request, else None."""
    rel = unquote(urlsplit(raw_path).path)[len('/v2'):].lstrip('/')
    rel = PAGES.get(rel.rstrip('/'), rel)
    parts = rel.split('/')
    if not rel or any(p in ('', '.', '..') or p.startswith('.') for p in parts) or '\\' in rel or '\x00' in rel:
        return None
    if len(parts) > 2 or (len(parts) == 2 and parts[0] != 'assets'):
        return None
    f = (V2_DIR / rel).resolve()
    if f.parent not in (V2_DIR, V2_DIR / 'assets') or f.suffix not in TYPES or not f.is_file():
        return None
    return f, TYPES[f.suffix]


def serve(handler):
    """Write the response for a /v2 GET on a BaseHTTPRequestHandler. Always handles the request."""
    if urlsplit(handler.path).path == '/v2':          # canonical trailing slash so relative URLs behave
        handler.send_response(301); handler.send_header('Location', '/v2/'); handler.send_header('Content-Length', '0'); handler.end_headers()
        return
    hit = resolve(handler.path)
    if hit is None:
        handler.send_error(404); return
    f, mime = hit
    try:
        body = f.read_bytes()
    except OSError:
        handler.send_error(404); return
    handler.send_response(200)
    handler.send_header('Content-Type', mime)
    # Pages, scripts and styles revalidate every load (edits on the Jetson show immediately);
    # the logo, font and icon sprite rarely change and may be cached for a day.
    handler.send_header('Cache-Control', 'public, max-age=86400' if f.parent.name == 'assets' else 'no-cache')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
