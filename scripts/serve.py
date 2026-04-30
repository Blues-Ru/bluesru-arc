#!/usr/bin/env python3
"""
Local test server for bluesru-site/.

Usage:
  python3 bluesru-arc/scripts/serve.py [--port 80]
  BLUESRU_ROOT=/Users/fedor/bluesru python3 bluesru-arc/scripts/serve.py

Features:
  - Serves bluesru-site/ directory
  - Resolves directory requests to index.html
  - Correct Content-Type: text/html; charset=utf-8 for HTML
  - Parses bluesru-arc/_redirects for 301/302 redirect rules
  - Rewrites /forum/topicN → /forum/topicN.html
"""

import sys
import re
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

import os as _os
ARC     = Path(__file__).resolve().parent.parent
_ws     = Path(_os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
SITE    = Path(_os.environ.get('BLUESRU_SITE', str(_ws / 'bluesru-site')))
MEDIA   = _ws / "bluesru-media"   # fallback for gallery photos, MP3s etc.
REDIRECTS_FILE = ARC / "_redirects"
DEFAULT_PORT   = 80


# ── Content-Type map ──────────────────────────────────────────────────────────
MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.htm':  'text/html; charset=utf-8',
    '.inc':  'text/html; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.xml':  'application/xml; charset=utf-8',
    '.txt':  'text/plain; charset=utf-8',
    '.ico':  'image/x-icon',
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.svg':  'image/svg+xml',
    '.mp3':  'audio/mpeg',
    '.pdf':  'application/pdf',
    '.yaml': 'text/plain; charset=utf-8',
}


def load_redirects(path):
    """
    Parse _redirects file.
    Format: /old-path  /new-path  [301|302]
    Returns list of (from_path, from_query, to_path, status_code).
    from_query is a dict of query params if the rule has ?key=val, else None.
    """
    rules = []
    if not path.exists():
        return rules
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        from_raw = parts[0]
        to_path = parts[1]
        try:
            code = int(parts[2]) if len(parts) > 2 else 301
        except ValueError:
            code = 301
        # Skip wildcard rules (can't match in stdlib)
        if '*' in from_raw:
            continue
        # Parse query string from rule if present
        if '?' in from_raw:
            from_path, qs = from_raw.split('?', 1)
            from_query = urllib.parse.parse_qs(qs, keep_blank_values=True)
        else:
            from_path = from_raw
            from_query = None
        rules.append((from_path, from_query, to_path, code))
    return rules


REDIRECTS = load_redirects(REDIRECTS_FILE)


def find_redirect(path, query_string=''):
    """
    Check if path+query matches a redirect rule.
    Returns (to_path, code) or None.
    """
    req_params = urllib.parse.parse_qs(query_string, keep_blank_values=True) if query_string else {}
    for from_path, from_query, to_path, code in REDIRECTS:
        # Match path
        if path.rstrip('/') != from_path.rstrip('/'):
            continue
        # If rule has query params, match them
        if from_query:
            match = all(
                k in req_params and req_params[k] == v
                for k, v in from_query.items()
            )
            if not match:
                continue
        return to_path, code
    return None


def resolve_path(url_path, site_dir, media_dir=None):
    """
    Resolve URL path to filesystem path.
    Returns (file_path, redirected_url) where redirected_url is set for
    /forum/topicN → /forum/topicN.html rewrites.
    Falls back to media_dir if the file is not found in site_dir.
    """
    # Decode URL encoding
    url_path = urllib.parse.unquote(url_path)

    # Forum topic rewrite: /forum/topicN or /forum/topic-N (no extension) → .html
    m = re.match(r'^/forum/topic(-?)(\d+)$', url_path)
    if m:
        topic_id = m.group(2)
        canonical = f'/forum/topic{topic_id}.html'
        fpath = site_dir / canonical.lstrip('/')
        if fpath.exists():
            return fpath, None
        fpath2 = site_dir / f'forum/topic-{topic_id}.html'
        if fpath2.exists():
            return fpath2, None

    rel = url_path.lstrip('/')
    fpath = site_dir / rel

    if fpath.is_file():
        return fpath, None

    if fpath.is_dir():
        for name in ('index.html', 'index.htm', 'default.html', 'default.htm'):
            idx = fpath / name
            if idx.exists():
                return idx, None

    if '.' not in fpath.name:
        for ext in ('.html', '.htm'):
            p = fpath.with_suffix(ext)
            if p.exists():
                return p, None

    # Fallback: look in media_dir (gallery photos, MP3s, etc.)
    if media_dir and media_dir.exists():
        mpath = media_dir / rel
        if mpath.is_file():
            return mpath, None

    return None, None


class BluesHandler(BaseHTTPRequestHandler):
    site_dir = SITE
    media_dir = MEDIA

    def log_message(self, fmt, *args):
        # Only log non-200 responses to reduce noise
        code = args[1] if len(args) > 1 else ''
        if str(code) not in ('200', '304'):
            super().log_message(fmt, *args)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        url_path = parsed.path
        query_string = parsed.query

        # 1. Check _redirects (supports query-string matching)
        redirect = find_redirect(url_path, query_string)
        if redirect:
            to_path, code = redirect
            self.send_response(code)
            self.send_header('Location', to_path)
            self.end_headers()
            return

        # 2. Resolve to file (falls back to media_dir)
        fpath, _ = resolve_path(url_path, self.site_dir, self.media_dir)

        if fpath is None:
            # 404
            not_found = self.site_dir / '404.html'
            if not_found.exists():
                content = not_found.read_bytes()
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'404 Not Found')
            return

        # 3. Serve file
        ext = fpath.suffix.lower()
        content_type = MIME_TYPES.get(ext, 'application/octet-stream')

        try:
            content = fpath.read_bytes()
        except OSError:
            self.send_response(500)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        fpath, _ = resolve_path(parsed.path, self.site_dir, self.media_dir)
        if fpath is None:
            self.send_response(404)
            self.end_headers()
        else:
            ext = fpath.suffix.lower()
            content_type = MIME_TYPES.get(ext, 'application/octet-stream')
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.end_headers()


def main():
    args = sys.argv[1:]
    port = DEFAULT_PORT
    site_dir = SITE

    i = 0
    while i < len(args):
        if args[i] == '--port' and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == '--site' and i + 1 < len(args):
            site_dir = Path(args[i + 1])
            i += 2
        else:
            i += 1

    if not site_dir.exists():
        print(f"ERROR: site directory not found: {site_dir}")
        print("Run blues-arc/scripts/build.sh first.")
        sys.exit(1)

    BluesHandler.site_dir = site_dir

    print(f"Blues.Ru test server")
    print(f"  Site:      {site_dir}")
    print(f"  Media:     {MEDIA}")
    print(f"  Redirects: {REDIRECTS_FILE} ({len(REDIRECTS)} rules loaded)")
    print(f"  URL:       http://localhost:{port}/")
    print(f"  Stop with: Ctrl+C")
    print()

    server = HTTPServer(('', port), BluesHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == '__main__':
    main()
