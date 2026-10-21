"""Static file route for ATLAS Glass UI V2 (/v2/...), served by rover-status-web on the Jetson.

Additive and read-only: GET of an allow-listed file under the V2 directory, nothing else.
No directory listing, no dotfiles, no path traversal, no new endpoints.
Since 2026-10-11 it also serves V2 at / (see serve_default); V1 page sources are kept on disk.
The directory defaults to <project_atlas>/web/v2 and can be overridden with ATLAS_WEB_V2_DIR.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

V2_DIR = Path(os.environ.get('ATLAS_WEB_V2_DIR') or Path(__file__).resolve().parent.parent / 'web' / 'v2').resolve()
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp', '.woff2': 'font/woff2', '.txt': 'text/plain; charset=utf-8'}
PAGES = {'': 'index.html', 'mapping': 'mapping.html', 'commissioning': 'commissioning.html', 'wifi': 'wifi.html', 'camera': 'camera.html', 'lidar': 'lidar.html', 'testlab': 'testlab.html', 'flysky-testlab': 'flysky-testlab.html', 'vision3d': 'vision3d.html'}


def decorate(body, mime):
    if mime.startswith('text/html'):
        return body.replace(b'</body>', b'<script src="/v2/home-nav.js"></script></body>')
    return body


# 2026-10-11: V2 is the default dashboard. The classic (V1) page routes are disabled, not deleted:
# its sources stay on disk (V2 pages are generated from them) and ATLAS_CLASSIC_UI=1 in the
# service environment restores the old routing exactly, with no file change.
CLASSIC_UI = os.environ.get('ATLAS_CLASSIC_UI', '').strip() == '1'
ROOT_PAGES = ('/', '/index.html')
# Old V1 page addresses lead to their V2 versions. 302 (not 301) so a rollback is not defeated by
# browsers caching a permanent redirect.
V1_PAGE_REDIRECTS = {'/mapping': '/v2/mapping', '/commissioning': '/v2/commissioning', '/wifi': '/v2/wifi'}


def serve_default(handler):
    """Serve V2 at / and redirect old V1 page paths. Returns False for every other path.

    Only page addresses are affected. APIs, camera streams, JS assets (/diagnostics.js,
    /commissioning.js, ...), /logo.png, /map.png and the manifest keep their existing routes.
    """
    if CLASSIC_UI:
        return False
    path = urlsplit(handler.path).path
    if path in ROOT_PAGES:
        f, mime = resolve('/v2/')
        try:
            body = decorate(f.read_bytes(), mime)
        except OSError:
            handler.send_error(503); return True
        handler.send_response(200)
        handler.send_header('Content-Type', mime)
        handler.send_header('Cache-Control', 'no-cache')
        handler.send_header('X-Content-Type-Options', 'nosniff')
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
        return True
    if path in V1_PAGE_REDIRECTS:
        handler.send_response(302)
        handler.send_header('Location', V1_PAGE_REDIRECTS[path])
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('Content-Length', '0')
        handler.end_headers()
        return True
    return False


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
        body = decorate(f.read_bytes(), mime)
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
