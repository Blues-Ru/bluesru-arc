#!/usr/bin/env python3
"""
Main bluesru-arc generator. Reads source data and templates, writes to SITE_DIR.

Usage: python3 scripts/generate.py [--section SECTION]

Sections:
  content     - copy/post-process static content from source dirs
  forum       - generate forum pages
  reviews     - generate review pages (albumview)
  news        - generate news pages
  bluesmen    - generate bluesmen list + process artist bio pages
  data        - generate JSON data files (calendar, news, artists)
  homepage    - generate index.html + links page
  redirects   - generate _redirects and CSVs
  rss         - generate review RSS

Run with no args to run all sections.
Run from bluesru-arc/ repo root (or anywhere — paths are repo-relative).
"""

import os
import re
import sys
import json
import shutil
import html as html_mod
import yaml
from pathlib import Path
from datetime import datetime

import jinja2

# ── Paths ──────────────────────────────────────────────────────────────────────
# ARC = the bluesru-arc repo root (parent of scripts/)
ARC        = Path(__file__).resolve().parent.parent
# BLUESRU_ROOT: workspace root when running locally; defaults to ARC parent for compat
_ws_root   = Path(os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
SITE       = Path(os.environ.get('BLUESRU_SITE', str(_ws_root / 'bluesru-site')))
TEMPLATES  = ARC / "templates"
INCLUDES   = ARC / "includes"
STATIC     = ARC / "static"
COVERS     = STATIC / "covers"   # cached Amazon cover images {asin}.jpg
CONTENT    = ARC / "content"   # populated by blues-dev/populate/populate.py
# Media fallback for local serving (not used in CF Pages build — media comes from R2)
MEDIA_DIR  = _ws_root / "bluesru-media"

# ── Media URL ──────────────────────────────────────────────────────────────────
MEDIA_BASE_URL = ""  # root-relative URLs; media files served from bluesru-media/ at same origin

# Content dirs — all sections are pre-populated in content/ by populate.py
# BLUES_RU kept for SSI resolution fallback (points to content/ when ws root unavailable)
BLUES_RU   = (_ws_root / "blues-ru") if (_ws_root / "blues-ru").exists() else CONTENT
BLUESNEWS  = CONTENT / "bluesnews"
ATB        = CONTENT / "atb"
BEEFHEART  = CONTENT / "beefheart"
ETHNOTRIP  = CONTENT / "ethnotrip"
ZAPPAZUHOI = CONTENT / "zappazuhoi"
# Calendar images: prefer committed copy inside ARC, fall back to workspace
CAL_IMGS   = (ARC / "blues-calendar") if (ARC / "blues-calendar").exists() \
             else (_ws_root / "blues-calendar")

# Extracted data: prefer inside ARC (for CF Pages), fall back to workspace
_extracted_local = _ws_root / "extracted-data"
_extracted_arc   = ARC / "extracted-data"
EXTRACTED        = _extracted_arc if _extracted_arc.exists() else _extracted_local
ARTISTS_YAML    = EXTRACTED / "blues-data" / "artists.yaml"
ALBUMS_DIR      = EXTRACTED / "blues-data" / "albums"
REVIEWS_DIR     = EXTRACTED / "blues-data" / "reviews"
EVENTS_DIR      = EXTRACTED / "blues-data" / "events"
ANNOUNCE_DIR    = EXTRACTED / "bluesru" / "announcements"
NEWS_DIR        = EXTRACTED / "blues-data" / "news"
TOPICS_INDEX    = EXTRACTED / "liveforum" / "topics-index.yaml"
TOPICS_DIR      = EXTRACTED / "liveforum" / "topics"
RESOURCES_YAML  = EXTRACTED / "blues-data" / "resources.yaml"
STREAMING_ARTISTS = EXTRACTED / "streaming" / "artists.yaml"
STREAMING_ALBUMS  = EXTRACTED / "streaming" / "albums.yaml"
GALLERIES_YAML    = EXTRACTED / "galleries" / "galleries.yaml"
GALLERIES_DIR     = EXTRACTED / "galleries"

# ── Jinja2 environment ─────────────────────────────────────────────────────────
JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES)),
    autoescape=False,
    undefined=jinja2.Undefined,
)

# ── Footer ─────────────────────────────────────────────────────────────────────
FOOTER = (INCLUDES / "footer.inc").read_text(encoding='utf-8').strip()
JINJA_ENV.globals['footer'] = FOOTER

# ── Google Analytics ────────────────────────────────────────────────────────────
GA_SNIPPET = '''\
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8HDC1W9R3E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-8HDC1W9R3E');
</script>'''
# ── Global site CSS ─────────────────────────────────────────────────────────────
SITE_CSS_TAG = '<link rel="stylesheet" href="/static/css/site.css">'

JINJA_ENV.globals['ga_snippet'] = GA_SNIPPET
JINJA_ENV.globals['site_css_tag'] = SITE_CSS_TAG

MONTHS_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
             'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

# ── Redirect rules (from _redirects) — used to rewrite internal links ──────────
def _load_redirect_rules():
    """
    Parse bluesru-arc/_redirects into a list of (pattern, replacement) tuples.
    Supports: exact paths, wildcard paths (/prefix/* → /target/:splat),
    and query-string rules (/path?key=val → /target/).
    """
    rules = []
    redirects_file = ARC / '_redirects'
    if not redirects_file.exists():
        return rules
    for line in redirects_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        src, dst = parts[0], parts[1]
        # Ignore external targets
        if dst.startswith('http'):
            continue
        if '*' in src:
            # Wildcard: /prefix/* → /target/:splat
            prefix = src.rstrip('*').rstrip('/')
            target = dst.replace(':splat', '')
            rules.append(('wildcard', prefix, target))
        elif '?' in src:
            # Query string: /path.aspx?key=val → /target/
            path_part, qs = src.split('?', 1)
            rules.append(('query', path_part, qs, dst))
        else:
            rules.append(('exact', src, dst))
    return rules

_REDIRECT_RULES = _load_redirect_rules()

def _apply_redirect(href):
    """
    Given an internal href, return the redirect target or the original href.
    Also normalizes /path/index.html → /path/.
    """
    if not href or not href.startswith('/') or href.startswith('//'):
        return href
    # Strip /index.html suffix
    href = re.sub(r'/index\.html?$', '/', href)
    # Ensure trailing slash on directory-like paths (no extension)
    path_part = href.split('?')[0].split('#')[0]
    if path_part and '.' not in path_part.split('/')[-1]:
        if not path_part.endswith('/'):
            href = path_part + '/' + (href[len(path_part):] if len(href) > len(path_part) else '')

    path = href.split('?')[0].split('#')[0]
    for rule in _REDIRECT_RULES:
        if rule[0] == 'exact' and rule[1] == path:
            # Preserve fragment if any
            frag = '#' + href.split('#')[1] if '#' in href else ''
            return rule[2] + frag
        elif rule[0] == 'wildcard':
            prefix = rule[1]
            if path.startswith(prefix + '/') or path == prefix:
                splat = path[len(prefix):].lstrip('/')
                target = rule[2]
                if splat:
                    target = target.rstrip('/') + '/' + splat
                return target
        elif rule[0] == 'query' and rule[1] == path and '?' in href:
            qs = href.split('?')[1].split('#')[0]
            # Check all key=val pairs in rule match
            rule_qs = rule[2]
            if rule_qs in qs:
                return rule[3]
    return href

# ── Dead link fixes (from bluesru-arc/data/link_fixes.yaml) ──────────────────────
_LINK_FIXES_PATH = ARC / 'data' / 'link_fixes.yaml'
def _load_link_fixes():
    if _LINK_FIXES_PATH.exists():
        return yaml.safe_load(_LINK_FIXES_PATH.read_text(encoding='utf-8')) or {}
    return {}
_LINK_FIXES = _load_link_fixes()

# ── SSI handling ───────────────────────────────────────────────────────────────
DROP_INCLUDES = {
    '/liveinternetsmall.inc', '/liveinternet.inc', '/banner.inc',
    '/translate.inc', '/fedor/spylog.inc', '/reading/logoadv.inc',
    '/style/logoadv.inc',
}
DROP_INCLUDE_KEYWORDS = ['liveinternet', 'spylog', 'logoadv', 'banner.inc', 'translate.inc']

ANALYTICS_PATTERNS = [
    re.compile(r'<!--\s*LiveInternet.*?//-->', re.IGNORECASE | re.DOTALL),
    re.compile(r'<script[^>]*>[\s\S]*?(?:liveinternet|counter\.yadro|spylog|rambler\.ru/top100)[\s\S]*?</script>', re.IGNORECASE),
    re.compile(r'<img[^>]*(?:counter\.rambler|top100\.cnt)[^>]*>', re.IGNORECASE),
    re.compile(r'<noscript[^>]*>[\s\S]*?top100[\s\S]*?</noscript>', re.IGNORECASE),
    re.compile(r'<!-- Yandex\.Metrika -->.*?<!-- /Yandex\.Metrika -->', re.IGNORECASE | re.DOTALL),
    re.compile(r'<!-- Google\.Analytics -->.*?<!-- /Google\.Analytics -->', re.IGNORECASE | re.DOTALL),
]
AD_SCRIPTS = re.compile(r'<script[^>]*(?:bluesad|googleapis)[^>]*></script>', re.IGNORECASE)

RE_INCLUDE_VIRTUAL = re.compile(r'<!--#include\s+virtual\s*=\s*"([^"]+)"\s*-->', re.IGNORECASE)
RE_INCLUDE_FILE    = re.compile(r'<!--#include\s+file\s*=\s*"([^"]+)"\s*-->', re.IGNORECASE)
RE_DYNAMIC_ASPX    = re.compile(r'<!--#include\s+virtual\s*=\s*"/data/dynamic\.aspx"\s*-->', re.IGNORECASE)
RE_UNRESOLVED      = re.compile(r'<!--\s*virtual include not resolved:\s*[^-]+?-->', re.IGNORECASE)

SKIP_EXTENSIONS = {
    '.mp3', '.ram', '.rm', '.swf', '.wma', '.wav',
    # Server-side files — never in site/
    '.aspx', '.ascx', '.asp', '.xsl', '.cs', '.vb',
    '.sln', '.csproj', '.resx', '.config',
}


def read_file(path):
    for enc in ['utf-8', 'windows-1251', 'latin-1']:
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return None


def strip_analytics(content):
    for pat in ANALYTICS_PATTERNS:
        content = pat.sub('', content)
    content = AD_SCRIPTS.sub('', content)
    # Strip all ASP.NET code blocks: <%...%> (single- and multi-line)
    content = re.sub(r'<%.*?%>', '', content, flags=re.DOTALL)
    content = re.sub(r'<asp:[^>]*/>', '', content, flags=re.IGNORECASE)
    # Unwrap <asp:Content> blocks — keep inner content, remove wrapper tags only.
    # Other <asp:*> blocks (Literal, Panel, etc.) are stripped with content.
    content = re.sub(r'<asp:Content\b[^>]*>(.*?)</asp:Content>', r'\1', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<asp:[^>]*>.*?</asp:[^>]*>', '', content, flags=re.IGNORECASE | re.DOTALL)
    # Strip dead AMG (AllMusic.com) links — the site is no longer at that URL
    content = re.sub(
        r'<a\b[^>]*allmusic\.com[^>]*>.*?</a>',
        '', content, flags=re.IGNORECASE | re.DOTALL)
    # Remove RealAudio (.ra/.rm/.ram) icon links — the format is obsolete
    # Pattern: <a href="...{.ra|.rm|.ram}">...</a> containing ra.gif image
    content = re.sub(
        r'<a\b[^>]*href="[^"]*\.(?:ra|rm|ram)"[^>]*>\s*<img[^>]*ra\.gif[^>]*/?>\s*</a>',
        '', content, flags=re.IGNORECASE | re.DOTALL)
    # Also remove standalone .ram href links (RealAudio playlist launchers)
    content = re.sub(
        r'<a\b[^>]*href="[^"]*\.ram"[^>]*>[^<]*</a>',
        '', content, flags=re.IGNORECASE)
    # Remove ra.gif images (standalone, without surrounding link)
    content = re.sub(
        r'<img\b[^>]*ra\.gif[^>]*/?>',
        '', content, flags=re.IGNORECASE)
    return content


def cover_url_for_asin(asin):
    """Return cover image URL: local cached path if available, else Amazon URL."""
    if not asin:
        return ''
    local = COVERS / f'{asin}.jpg'
    if local.exists():
        return f'/static/covers/{asin}.jpg'
    # Fallback to Amazon (will work if not yet cached)
    return f'https://images-na.ssl-images-amazon.com/images/P/{asin}.01.MZZZZZZZ.jpg'


def format_review_body(body):
    """Wrap review body in paragraph tags, splitting on double newlines.
    Also strips dead AMG links (keeping the link text)."""
    body = body.strip()
    # Strip AMG/AllMusic references (dead site):
    # 1. <a href="...allmusic...">text</a> → keep text
    body = re.sub(
        r'<a\b[^>]*allmusic\.com[^>]*>(.*?)</a>',
        r'\1', body, flags=re.IGNORECASE | re.DOTALL)
    # 2. <img src="http://image.allmusic.com/..."> → remove entirely
    body = re.sub(
        r'<img\b[^>]*image\.allmusic\.com[^>]*/?>', '',
        body, flags=re.IGNORECASE)
    # 3. Plain-text URLs to allmusic.com (not in tags) → remove
    body = re.sub(
        r'https?://(?:www\.)?allmusic\.com/\S+', '', body, flags=re.IGNORECASE)
    if not body:
        return body
    if '\n\n' not in body:
        # Single paragraph — wrap if not already tagged
        body_lower = body.lower()
        if body_lower.startswith('<p>') and body_lower.endswith('</p>'):
            return body
        return f'<p>{body}</p>'
    parts = re.split(r'\n{2,}', body)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        part_lower = part.lower()
        if part_lower.startswith('<p>') or part_lower.endswith('</p>'):
            result.append(part)
        else:
            result.append(f'<p>{part}</p>')
    return '\n'.join(result)


def resolve_include(vpath, source_dir, source_root):
    vpath_lower = vpath.strip().lower()
    # Use archive footer
    if vpath_lower == '/footer.inc':
        return FOOTER
    if vpath_lower in DROP_INCLUDES:
        return ''
    if any(kw in vpath_lower for kw in DROP_INCLUDE_KEYWORDS):
        return ''
    if '/data/dynamic.aspx' in vpath_lower:
        return ''  # handled separately

    candidates = []
    if vpath_lower.startswith('/'):
        rel = vpath.lstrip('/')
        # Prefer the encoding-corrected content/ version over raw source dirs
        candidates = [CONTENT / rel, BLUES_RU / rel, source_root / rel]
    else:
        candidates = [source_dir / vpath, source_root / vpath]

    for disk_path in candidates:
        if disk_path.exists() and disk_path.is_file():
            content = read_file(disk_path)
            if content is None:
                continue
            content = strip_analytics(content)
            # Recursively resolve any SSI includes in the included file
            content = RE_INCLUDE_VIRTUAL.sub(
                lambda m: resolve_include(m.group(1), disk_path.parent, source_root), content)
            content = RE_INCLUDE_FILE.sub(
                lambda m: resolve_include(m.group(1), disk_path.parent, source_root), content)
            content = RE_DYNAMIC_ASPX.sub('', content)
            return content
    return ''


def _build_resource_links(resources, artist_slug):
    """Build HTML resource links, rewriting /bluesmen/ and /artist/ legacy dirs to new slug."""
    if not resources:
        return ''
    seen_urls = set()
    items = []
    for r in resources:
        url = r.get('url', '') or ''
        type_short = r.get('type_short', '')
        name = r.get('name', '')
        if not url or not type_short:
            continue
        # Skip Страница (type 1) — it's just the artist's own page, redundant
        if r.get('type_id') == 1:
            continue
        # Skip dynamic .aspx pages (don't exist in static archive)
        if '.aspx' in url.lower():
            continue
        # Strip blues.ru prefix from internal http URLs
        url = re.sub(r'^https?://(?:www\.)?blues\.ru', '', url, flags=re.IGNORECASE)
        # Rewrite /bluesmen/{OldDir}/... → /artist/{slug}/...
        if url.startswith('/bluesmen/') and artist_slug:
            rest = re.sub(r'^/bluesmen/[^/]+', '', url)
            url = f'/artist/{artist_slug}{rest}'
        # Rewrite /artist/{OldDir}/... → /artist/{slug}/...
        elif url.startswith('/artist/') and artist_slug:
            rest = re.sub(r'^/artist/[^/]+', '', url)
            url = f'/artist/{artist_slug}{rest}'
        # Deduplicate
        if url in seen_urls:
            continue
        seen_urls.add(url)
        label = name or type_short
        items.append(f'<a href="{url}">{html_mod.escape(label)}</a>')
    if not items:
        return ''
    return ' | '.join(items)


def process_html(content, source_dir, source_root, artist_slug=None,
                 artist_name=None, artist_legacy_dir=None, artist_resources=None):
    content = strip_analytics(content)
    content = re.sub(r'charset\s*=\s*["\']?windows-1251["\']?', 'charset=utf-8',
                     content, flags=re.IGNORECASE)
    # Rewrite bare default.htm links to directory index
    content = re.sub(r'href="http://www\.blues\.ru/default\.htm"', 'href="/"',
                     content, flags=re.IGNORECASE)
    content = re.sub(r'href="default\.html?"', 'href="./"',
                     content, flags=re.IGNORECASE)

    # Replace dynamic.aspx with nav block + JS album loader if artist_slug given
    if artist_slug:
        nav_block = '<hr size="1">\n'
        if artist_name and artist_legacy_dir:
            escaped_name = html_mod.escape(artist_name)
            nav_block += (
                f'<b><a href="/artist/">Музыканты</a> : '
                f'<a href="/artist/{artist_legacy_dir}/">{escaped_name}</a></b>\n'
            )
        res_links = _build_resource_links(artist_resources, artist_legacy_dir)
        stream_html = streaming_links_html(artist_slug, kind='artist')
        if stream_html:
            res_links = (res_links + ' | ' if res_links else '') + stream_html
        if res_links:
            nav_block += f'<p>{res_links}</p>\n'
        album_div = (
            f'\n{nav_block}'
            f'<div id="artist-albums" data-slug="{artist_slug}">'
            f'<small><i>Загрузка дискографии...</i></small></div>\n'
            f'<script src="/static/js/albums.js"></script>\n'
        )
        content = RE_DYNAMIC_ASPX.sub(album_div, content)
    else:
        content = RE_DYNAMIC_ASPX.sub('', content)

    content = RE_INCLUDE_VIRTUAL.sub(lambda m: resolve_include(m.group(1), source_dir, source_root), content)
    content = RE_INCLUDE_FILE.sub(lambda m: resolve_include(m.group(1), source_dir, source_root), content)
    content = RE_UNRESOLVED.sub('', content)

    # ── Rewrite internal links: apply redirects + dead-link treatment ─────────
    content = _rewrite_links(content)

    # Inject site CSS + Google Analytics before </head>
    if '</head>' in content.lower():
        inject = SITE_CSS_TAG + '\n' + GA_SNIPPET + '\n'
        content = re.sub(r'(</head>)', inject + '\\1', content, count=1, flags=re.IGNORECASE)
    return content


# ── Streaming data ─────────────────────────────────────────────────────────────

# URL templates — IDs stored in YAML, URLs derived at render time
ALBUM_URL_TEMPLATES = {
    'apple_music':       'https://music.apple.com/us/album/{}',
    'spotify':           'https://open.spotify.com/album/{}',
    'deezer':            'https://www.deezer.com/album/{}',
    'ytmusic':           'https://music.youtube.com/browse/{}',
    'youtube_video':     'https://www.youtube.com/watch?v={}',
    'youtube_playlist':  'https://www.youtube.com/playlist?list={}',
}
ARTIST_URL_TEMPLATES = {
    'apple_music':  'https://music.apple.com/us/artist/{}',
    'spotify':      'https://open.spotify.com/artist/{}',
    'deezer':       'https://www.deezer.com/artist/{}',
}

STREAMING_PLATFORM_LABELS = {
    'apple_music':      'Apple Music',
    'spotify':          'Spotify',
    'deezer':           'Deezer',
    'ytmusic':          'YouTube Music',
    'youtube_video':    'YouTube',
    'youtube_playlist': 'YouTube',
}

def _load_streaming(path):
    if path.exists():
        return yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return {}

_STREAMING_ARTISTS = None
_STREAMING_ALBUMS = None

def get_streaming_artists():
    global _STREAMING_ARTISTS
    if _STREAMING_ARTISTS is None:
        _STREAMING_ARTISTS = _load_streaming(STREAMING_ARTISTS)
    return _STREAMING_ARTISTS

def get_streaming_albums():
    global _STREAMING_ALBUMS
    if _STREAMING_ALBUMS is None:
        _STREAMING_ALBUMS = _load_streaming(STREAMING_ALBUMS)
    return _STREAMING_ALBUMS

def streaming_links_html(slug, kind='artist'):
    """Build HTML streaming links for an artist or album slug."""
    data = get_streaming_artists() if kind == 'artist' else get_streaming_albums()
    info = data.get(slug, {})
    if not info:
        return ''
    templates = ARTIST_URL_TEMPLATES if kind == 'artist' else ALBUM_URL_TEMPLATES
    parts = []
    for platform, tmpl in templates.items():
        aid = info.get(f'{platform}_id')
        if aid:
            url = tmpl.format(aid)
            label = STREAMING_PLATFORM_LABELS[platform]
            parts.append(f'<a href="{url}" target="_blank">{label}</a>')
    return ' | '.join(parts)


# ── Data loaders ───────────────────────────────────────────────────────────────
def load_artists():
    with open(ARTISTS_YAML) as f:
        return yaml.safe_load(f)

def load_albums():
    albums = {}
    for p in ALBUMS_DIR.glob('*.yaml'):
        a = yaml.safe_load(p.read_text(encoding='utf-8'))
        if a and a.get('id'):
            albums[str(a['id'])] = a
    return albums

def load_reviews():
    """Returns list of (meta, body) and album_id→review_slug map."""
    reviews = []
    review_by_album = {}
    for p in sorted(REVIEWS_DIR.glob('review-*.md')):
        text = p.read_text(encoding='utf-8')
        m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
        if not m:
            continue
        meta = yaml.safe_load(m.group(1))
        body = m.group(2).strip()
        reviews.append((meta, body))
        album_id = str(meta.get('album_id', ''))
        if album_id:
            review_by_album[album_id] = meta.get('slug', '')
    return reviews, review_by_album

RE_FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)', re.DOTALL)


def load_resources():
    """Return dict: artist_id (str) → list of resource dicts."""
    if not RESOURCES_YAML.exists():
        return {}
    data = yaml.safe_load(RESOURCES_YAML.read_text(encoding='utf-8'))
    if not data:
        return {}
    return {str(entry['artist_id']): entry['resources'] for entry in data}


# ── Forum rendering ────────────────────────────────────────────────────────────

# Safe HTML tags allowed in forum post bodies
_FORUM_ALLOWED_TAGS = {'b', 'i', 'u', 'strong', 'em', 'br', 's', 'strike'}
_RE_TAG = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)
_RE_HREF = re.compile(r'\bhref\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_RE_VIDEO_SRC = re.compile(
    r'\bsrc\s*=\s*["\']([^"\']*(?:youtube\.com|youtu\.be|vimeo\.com)[^"\']*)["\']',
    re.IGNORECASE
)
_RE_NUMERIC_REF = re.compile(r'&#\d+;')
# Matches bare http/https URLs not already inside an <a href="...">
_RE_BARE_URL = re.compile(r'(?<!["\'>])(https?://[^\s<>"\']+)', re.IGNORECASE)


def _autolink_bare_urls(html_text):
    """Wrap bare URLs in <a href="..." rel="nofollow"> tags.
    Skips URLs already inside href attributes."""
    def replace_url(m):
        url = m.group(1).rstrip('.,;:!?)\'\"')  # strip trailing punctuation
        trailing = m.group(1)[len(url):]
        return f'<a href="{url}" rel="nofollow">{url}</a>{trailing}'
    return _RE_BARE_URL.sub(replace_url, html_text)


def sanitize_forum_html(text):
    """
    Allow a safe subset of HTML in forum posts:
    - <b>, <i>, <u>, <strong>, <em>, <br>, <s>, <strike>
    - <a href="..."> — any href (archive only, no XSS concern beyond display)
    - <iframe> — only if src is youtube.com/youtu.be
    - Numeric character references &#NNNNN; preserved
    Everything else: strip the tag but keep its text content.
    """
    result = []
    pos = 0
    for m in _RE_TAG.finditer(text):
        # Append text before this tag (escape it)
        raw_before = text[pos:m.start()]
        # Preserve numeric char refs, escape everything else
        result.append(_escape_preserving_refs(raw_before))
        pos = m.end()

        closing = m.group(1)  # '/' if closing tag
        tag = m.group(2).lower()
        attrs_raw = m.group(3)

        if tag in _FORUM_ALLOWED_TAGS:
            result.append(f'<{closing}{tag}>')
        elif tag == 'a' and not closing:
            href_m = _RE_HREF.search(attrs_raw)
            if href_m:
                href = href_m.group(1)
                # Basic sanitization: reject javascript: URLs
                if not re.match(r'^\s*javascript:', href, re.IGNORECASE):
                    result.append(f'<a href="{html_mod.escape(href)}">')
                # else: skip the tag
        elif tag == 'a' and closing:
            result.append('</a>')
        elif tag == 'iframe' and not closing:
            src_m = _RE_VIDEO_SRC.search(attrs_raw)
            if src_m:
                src = src_m.group(1)
                result.append(
                    f'<iframe width="560" height="315" src="{html_mod.escape(src)}" '
                    f'frameborder="0" allowfullscreen></iframe>'
                )
            # Non-YouTube iframe: skip entirely
        # All other tags: strip (keep text between them)

    # Append remaining text after last tag
    result.append(_escape_preserving_refs(text[pos:]))
    return ''.join(result)


def _escape_preserving_refs(text):
    """HTML-escape text but preserve numeric character references like &#12345;"""
    if not text:
        return text
    # Temporarily replace numeric refs with placeholders
    refs = _RE_NUMERIC_REF.findall(text)
    placeholder_map = {}
    for i, ref in enumerate(refs):
        key = f'\x00REF{i}\x00'
        placeholder_map[key] = ref
        text = text.replace(ref, key, 1)
    # Escape HTML
    text = html_mod.escape(text)
    # Restore refs
    for key, ref in placeholder_map.items():
        text = text.replace(html_mod.escape(key), ref)
    return text


def format_forum_date(date_str):
    """Convert YYYY-MM-DD HH:MM (or YYYY-MM-DD) to DD.MM.YY HH:MM (or DD.MM.YY)"""
    if not date_str:
        return ''
    s = str(date_str)
    try:
        if len(s) >= 16 and s[10] == ' ':
            d = datetime.strptime(s[:16], '%Y-%m-%d %H:%M')
            return d.strftime('%d.%m.%y %H:%M')
        else:
            d = datetime.strptime(s[:10], '%Y-%m-%d')
            return d.strftime('%d.%m.%y')
    except Exception:
        return s


def render_post_html(post, topic_slug, full=True, depth=0):
    pid = post.get('id', '')
    poster = html_mod.escape(post.get('poster', '') or '')
    date_str = format_forum_date(post.get('date', ''))
    subject = html_mod.escape(post.get('subject', '') or '')
    text = post.get('text', '') or ''
    deleted = post.get('deleted', False)
    replies = post.get('replies', [])

    if deleted:
        text_html = ''
    else:
        # Render safe HTML subset; autolink bare URLs; convert remaining newlines to <br>
        sanitized = sanitize_forum_html(text)
        sanitized = _autolink_bare_urls(sanitized)
        sanitized = re.sub(r'\n', '<br>\n', sanitized)
        text_html = f'<p>{sanitized}</p>' if text else ''

    if full and depth == 0:
        # Root post on topic page: show text without header (header is in topic-header)
        html = f'<div class="message"><a name="post{pid}"></a>'
        if text_html:
            html += f'<div class="text">{text_html}</div>'
        for reply in replies:
            html += render_post_html(reply, topic_slug, full=True, depth=1)
        html += '</div>'
    elif full:
        # Reply post on topic page — skip deleted posts entirely (don't show spam subjects)
        if deleted:
            return ''.join(render_post_html(r, topic_slug, full=True, depth=depth+1) for r in replies)
        html = f'<div class="message"><a name="post{pid}"></a><div class="header">'
        html += f'<img class="bullet" src="/forum/bullet.gif" id="bullet{pid}">'
        html += f'<span class="subject">{subject}</span>'
        html += f'\n    - <span class="name">{poster}</span>'
        html += f'\n      <span class="date">({date_str})</span>'
        html += f'\n      <span class="self-link"><a href="/forum/{topic_slug}#post{pid}">#</a></span>'
        html += '</div>'
        if text_html:
            html += f'<div class="text">{text_html}</div>'
        for reply in replies:
            html += render_post_html(reply, topic_slug, full=True, depth=depth+1)
        html += '</div>'
    else:
        # Index mode: show header only, no text; skip deleted posts
        if deleted:
            html_parts = []
            for reply in replies:
                html_parts.append(render_post_html(reply, topic_slug, full=False, depth=depth+1))
            return ''.join(html_parts)
        html = f'<div class="message"><a name="post{pid}"></a><div class="header">'
        html += f'<img class="bullet" src="/forum/bullet.gif" id="bullet{pid}">'
        html += f'<span class="subject"><a href="/forum/{topic_slug}">{subject}</a></span>'
        html += f'\n    - <span class="name">{poster}</span>'
        html += f'\n      <span class="date">({date_str})</span>'
        html += '</div>'
        for reply in replies:
            html += render_post_html(reply, topic_slug, full=False, depth=depth+1)
        html += '</div>'

    return html


def render_topic_html(topic_data, topic_meta, full=False, forum_page=1):
    topic_id = topic_meta.get('topic_id', '')
    # Use topicN (no dash) to match live site URLs
    slug = f'topic{topic_id}' if topic_id else topic_meta.get('slug', f'topic-{topic_id}')
    posts = topic_data.get('posts', []) if topic_data else []

    if not posts:
        return ''

    if full:
        # Full topic page: topic-header + all posts with text
        first = posts[0]
        first_poster = html_mod.escape(first.get('poster', '') or '')
        first_date = format_forum_date(first.get('date', ''))
        subject = html_mod.escape(posts[0].get('subject', '') or topic_meta.get('title', '') or '')

        page_url = '/forum/' if forum_page <= 1 else f'/forum/page{forum_page}.html'
        forum_back = f'{page_url}#topic{topic_id}'
        html = f'<div class="topic-header"><a href="{forum_back}">ФОРУМ : Разговоры о блюзе</a> :\n'
        html += f'  <span class="subject">{subject}</span>\n'
        html += f'    - <span class="name">{first_poster}</span>\n'
        html += f'      <span class="date">({first_date})</span>\n'
        html += f'      <span class="self-link"><a href="/forum/{slug}">#</a></span>'
        html += f'</div>'
        html += f'<div class="topic"><a name="topic{topic_id}"></a>'
        for post in posts:
            html += render_post_html(post, slug, full=True)
        html += '</div>'
    else:
        # Index mode: show topic block with headers only
        html = f'<div class="topic"><a name="topic{topic_id}"></a>'
        for post in posts:
            html += render_post_html(post, slug, full=False)
        html += '</div>'

    return html


# ── Sections ───────────────────────────────────────────────────────────────────

def _topic_is_all_deleted(topic_data):
    """Return True if a topic has no non-deleted posts at any depth."""
    def has_visible(posts):
        for p in posts:
            if not p.get('deleted', False):
                return True
            if has_visible(p.get('replies', [])):
                return True
        return False
    if topic_data is None:
        return True
    return not has_visible(topic_data.get('posts', []))


def generate_forum():
    print("Generating forum pages...")
    with open(TOPICS_INDEX) as f:
        topics_index = yaml.safe_load(f)

    # Sort by integer topic_id descending (NOT string sort)
    topics_sorted = sorted(
        topics_index,
        key=lambda t: int(t.get('topic_id', 0)),
        reverse=True,
    )

    # Filter out topics whose every post is deleted
    def topic_is_visible(tm):
        tf = TOPICS_DIR / f'topic-{tm["topic_id"]}.yaml'
        if not tf.exists():
            return False
        td = yaml.safe_load(tf.read_text())
        return not _topic_is_all_deleted(td)

    topics_visible = [tm for tm in topics_sorted if topic_is_visible(tm)]
    print(f"  Topics: {len(topics_sorted)} total, {len(topics_visible)} visible")

    PAGE_SIZE = 50
    total = len(topics_visible)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    tmpl_index = JINJA_ENV.get_template('forum_index.html.j2')
    tmpl_topic = JINJA_ENV.get_template('forum_topic.html.j2')

    # Generate paginated index pages
    for page_num in range(pages):
        start = page_num * PAGE_SIZE
        page_topics_meta = topics_visible[start:start + PAGE_SIZE]

        # Load and render topic data
        rendered_topics = []
        for tm in page_topics_meta:
            tf = TOPICS_DIR / f'topic-{tm["topic_id"]}.yaml'
            td = yaml.safe_load(tf.read_text()) if tf.exists() else None
            rendered_topics.append(render_topic_html(td, tm, full=False))

        fname = 'index.html' if page_num == 0 else f'page{page_num + 1}.html'
        dst = SITE / 'forum' / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        out = tmpl_index.render(
            page=page_num + 1,
            has_next=page_num + 1 < pages,
            topics=rendered_topics,
            render_topic=lambda t, full=False: t,  # already rendered
        )
        dst.write_text(out, encoding='utf-8')

    print(f"  Forum index: {pages} pages")

    # Build topic_id → forum page number map (for correct backlinks)
    PAGE_SIZE = 50
    topic_to_page = {}
    for i, tm in enumerate(topics_visible):
        topic_to_page[tm.get('topic_id')] = (i // PAGE_SIZE) + 1

    # Generate individual topic pages as flat files: topicN.html (no dash, matches live site URL)
    generated = 0
    for tm in topics_visible:
        topic_id = tm.get('topic_id')
        tf = TOPICS_DIR / f'topic-{topic_id}.yaml'
        if not tf.exists():
            continue
        td = yaml.safe_load(tf.read_text())
        posts = td.get('posts', [])
        if not posts:
            continue

        first = posts[0]
        fp = topic_to_page.get(topic_id, 1)
        rendered = render_topic_html(td, tm, full=True, forum_page=fp)
        out = tmpl_topic.render(
            topic=tm,
            first_poster=html_mod.escape(first.get('poster', '') or ''),
            render_topic=lambda t, full=True: rendered,
        )
        # Use topicN.html (no dash) to match live site URL /forum/topicN
        dst = SITE / 'forum' / f'topic{topic_id}.html'
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out, encoding='utf-8')
        generated += 1

    # Copy forum static files
    for f in (STATIC / 'forum').iterdir():
        shutil.copy2(f, SITE / 'forum' / f.name)

    print(f"  Forum topics: {generated}")


def _strip_artist_prefix(a_slug, album_slug):
    """Strip '{a_slug}-' prefix from album slug for URL path segment."""
    if a_slug and a_slug != 'various-musicians' and album_slug.startswith(a_slug + '-'):
        return album_slug[len(a_slug) + 1:]
    return album_slug


def generate_reviews():
    print("Generating review pages...")
    from collections import defaultdict
    reviews, review_by_album = load_reviews()
    albums = load_albums()
    artists = {str(a['id']): a for a in load_artists()}

    def _format_mark(mark):
        n = int(mark)
        full = n // 2
        half = n % 2
        return '@' * full + ('+' if half else '')

    def artist_slug_for_url(artist):
        """Return the URL slug for this artist (used in /artist/{slug}/ path)."""
        if not artist:
            return 'various-musicians'
        slug = artist.get('slug', '')
        if slug:
            return slug
        # Fallback: derive from legacy_path
        lp = artist.get('legacy_path', '').strip('/')
        parts = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        if legacy_dir and '.' not in legacy_dir and not legacy_dir.startswith('www.'):
            import re as _re
            return _re.sub(r'[^a-z0-9]+', '-', legacy_dir.lower()).strip('-')
        return 'various-musicians'

    tmpl = JINJA_ENV.get_template('albumview.html.j2')
    tmpl_idx = JINJA_ENV.get_template('review_index.html.j2')
    generated = 0

    # Collect data for monthly index
    by_month = defaultdict(list)  # "YYYY-MM" → list of review entries

    for meta, body in reviews:
        review_slug = meta.get('slug', '')
        album_id = str(meta.get('album_id', ''))
        album = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or meta.get('artist_id', '') or '')
        artist = artists.get(artist_id, {})

        # New URL: /artist/{artist_url_slug}/{album_url_slug}/
        a_slug = artist_slug_for_url(artist) if artist_id else 'various-musicians'
        album_slug = album.get('slug', '') or review_slug
        url_album_slug = _strip_artist_prefix(a_slug, album_slug)
        new_url = f'/artist/{a_slug}/{url_album_slug}/'
        # artist dir for the header link on the page (use slug = normalized URL dir)
        legacy_dir = a_slug  # now the artist dir IS the slug

        mark = meta.get('mark')
        review_data = {
            'id': meta.get('id', ''),
            'album_title': album.get('title', '') or meta.get('album', ''),
            'year': album.get('year', ''),
            'author': meta.get('author', ''),
            'body': format_review_body(body),
            'mark': mark,
            'mark_text': _format_mark(mark) if mark else '',
        }

        alb_slug = album.get('slug', '')
        out = tmpl.render(
            album=album,
            cover_url=cover_url_for_asin(album.get('asin', '')),
            artist_name=artist.get('name') or album.get('artist') or '',
            artist_legacy_path=legacy_dir,
            reviews=[review_data] if body else [],
            streaming_links=streaming_links_html(alb_slug, kind='album'),
            artist_streaming_links=streaming_links_html(a_slug, kind='artist'),
            footer=FOOTER,
        )
        # Write to /artist/{a_slug}/{url_album_slug}/
        dst = SITE / 'artist' / a_slug / url_album_slug / 'index.html'
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(out, encoding='utf-8')

        generated += 1

        # Collect for monthly index
        date_str = str(meta.get('date', ''))
        month_key = date_str[:7] if len(date_str) >= 7 else '0000-00'
        by_month[month_key].append({
            'url': new_url,
            'artist_name': artist.get('name') or album.get('artist') or '',
            'album_title': album.get('title') or meta.get('album') or '',
            'year': album.get('year', ''),
            'author': meta.get('author', ''),
            'asin': album.get('asin', ''),
            'cover_url': cover_url_for_asin(album.get('asin', '')),
            'date_str': date_str,
        })

    # ── /review/ and /review/YYYY-MM/ chronological index pages ────────────
    month_keys = sorted(by_month.keys(), reverse=True)  # newest first

    # Build month list for navigation (newest first)
    month_list = []
    for mk in month_keys:
        if mk == '0000-00':
            continue
        y, mo = mk[:4], int(mk[5:7])
        month_list.append({'key': mk, 'label': f'{y} {MONTHS_RU[mo]}'})

    def month_nav_html(current_key, prev_key, next_key):
        """prev_key = newer (left ←), next_key = older (right →)."""
        parts = []
        if prev_key and prev_key != '0000-00':
            y2, mo2 = prev_key[:4], int(prev_key[5:7])
            parts.append(f'← <a href="/review/{prev_key}/">{y2} {MONTHS_RU[mo2]}</a>')
        if current_key and current_key != '0000-00':
            y, mo = current_key[:4], int(current_key[5:7])
            parts.append(f'<b>{y} {MONTHS_RU[mo]}</b>')
        if next_key and next_key != '0000-00':
            y2, mo2 = next_key[:4], int(next_key[5:7])
            parts.append(f'<a href="/review/{next_key}/">{y2} {MONTHS_RU[mo2]}</a> →')
        return ' | '.join(parts)

    # ── Build year → months mapping ───────────────────────────────────────────
    from collections import OrderedDict
    years_months = OrderedDict()  # year → [month_key, ...] newest first
    for mk in month_keys:
        if mk == '0000-00':
            continue
        yr = mk[:4]
        years_months.setdefault(yr, []).append(mk)
    year_list = list(years_months.keys())  # newest first

    def year_nav_data(current_year=None):
        """Return list of {year, current} for template."""
        return [{'year': y, 'current': y == current_year} for y in year_list]

    def months_for_year(yr):
        """Return list of {key, label} for months in a year."""
        result = []
        for mk in years_months.get(yr, []):
            mo = int(mk[5:7])
            result.append({'key': mk, 'label': f'{MONTHS_RU[mo]}'})
        return result

    (SITE / 'review').mkdir(parents=True, exist_ok=True)

    # ── /review/ main index: most recent year with its months + reviews ───────
    current_yr = year_list[0] if year_list else None
    curr_mkeys = years_months.get(current_yr, [])
    index_blocks = []
    for mk in curr_mkeys:
        mo = int(mk[5:7])
        entries = sorted(by_month[mk], key=lambda x: x['date_str'], reverse=True)
        index_blocks.append({'label': f'{current_yr} {MONTHS_RU[mo]}', 'key': mk, 'reviews': entries})

    (SITE / 'review' / 'index.html').write_text(tmpl_idx.render(
        current_month=None,
        current_year=current_yr,
        month_blocks=index_blocks,
        nav_links=None,
        more_html=None,
        month_list=None,
        year_nav=year_nav_data(current_yr),
        current_year_months=months_for_year(current_yr),
        footer=FOOTER,
    ), encoding='utf-8')

    # ── Per-year pages: /review/YYYY/ ────────────────────────────────────────
    for yi, yr in enumerate(year_list):
        yr_mkeys = years_months[yr]
        yr_blocks = []
        for mk in yr_mkeys:
            mo = int(mk[5:7])
            entries = sorted(by_month[mk], key=lambda x: x['date_str'], reverse=True)
            yr_blocks.append({'label': f'{yr} {MONTHS_RU[mo]}', 'key': mk, 'reviews': entries})
        dst_yr = SITE / 'review' / yr / 'index.html'
        dst_yr.parent.mkdir(parents=True, exist_ok=True)
        dst_yr.write_text(tmpl_idx.render(
            current_month=None,
            current_year=yr,
            month_blocks=yr_blocks,
            nav_links=None,
            more_html=None,
            month_list=None,
            year_nav=year_nav_data(yr),
            current_year_months=months_for_year(yr),
            footer=FOOTER,
        ), encoding='utf-8')

    # ── Per-month pages: /review/YYYY-MM/ ─────────────────────────────────────
    for i, mk in enumerate(month_keys):
        if mk == '0000-00':
            continue
        y, mo = mk[:4], int(mk[5:7])
        prev_key = month_keys[i - 1] if i > 0 else None  # newer
        next_key = month_keys[i + 1] if i + 1 < len(month_keys) else None  # older
        if prev_key == '0000-00':
            prev_key = None
        if next_key == '0000-00':
            next_key = None
        nav = month_nav_html(mk, prev_key, next_key)
        entries = sorted(by_month[mk], key=lambda x: x['date_str'], reverse=True)
        dst_month = SITE / 'review' / mk / 'index.html'
        dst_month.parent.mkdir(parents=True, exist_ok=True)
        dst_month.write_text(tmpl_idx.render(
            current_month=f'{y} {MONTHS_RU[mo]}',
            current_year=y,
            month_blocks=[{'label': f'{y} {MONTHS_RU[mo]}', 'key': mk, 'reviews': entries}],
            nav_links=nav,
            more_html=None,
            month_list=None,
            year_nav=year_nav_data(y),
            current_year_months=months_for_year(y),
            footer=FOOTER,
        ), encoding='utf-8')

    # ── /review/author/{slug}/ — per-author pages ─────────────────────────────
    # Group reviews by author
    by_author = defaultdict(list)
    for meta, body in reviews:
        author = (meta.get('author', '') or '').strip()
        if not author:
            continue
        album_id = str(meta.get('album_id', ''))
        album = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or meta.get('artist_id', '') or '')
        artist = artists.get(artist_id, {})
        a_slug = artist_slug_for_url(artist) if artist_id else 'various-musicians'
        album_slug = album.get('slug', '') or meta.get('slug', '')
        date_str = str(meta.get('date', ''))
        by_author[author].append({
            'url': f'/artist/{a_slug}/{_strip_artist_prefix(a_slug, album_slug)}/',
            'artist_name': artist.get('name') or album.get('artist') or '',
            'album_title': album.get('title') or meta.get('album') or '',
            'year': album.get('year', ''),
            'asin': album.get('asin', ''),
            'cover_url': cover_url_for_asin(album.get('asin', '')),
            'date_str': date_str,
        })

    def author_slug(name, idx):
        """Generate slug from author name: prefer Latin characters."""
        import re as _re
        # Extract Latin + digits only
        latin = _re.sub(r'[^a-zA-Z0-9\s_-]', '', name).strip()
        latin = _re.sub(r'[\s_]+', '-', latin).strip('-').lower()
        if len(latin) >= 3:
            return latin
        return f'author-{idx + 1}'

    author_tmpl_html = """<!DOCTYPE html>
<html>
<head>
  <title>Blues.Ru: CD обзор — {{ author | e }}</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <link rel="shortcut icon" href="/images/bluesru.ico">
  <style>body { max-width: 900px; margin: 0 auto; padding: 0 1em; }</style>
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc" alink="#00bb00">
<p><a href="/"><b>Blues.Ru</b></a> &gt; <a href="/review/">CD обзор</a></p>
<h2>{{ author | e }}</h2>
<ul>
{% for r in reviews %}
<li>
  {% if r.cover_url %}<a href="{{ r.url }}"><img src="{{ r.cover_url }}" alt="" border="0" style="vertical-align:middle;margin-right:4px;" width="40" height="40"></a>{% endif %}
  <a href="{{ r.url }}">{% if r.artist_name %}<b>{{ r.artist_name | e }}</b> — {% endif %}<b>{{ r.album_title | e }}</b></a>{% if r.year %}, {{ r.year }}{% endif %}
</li>
{% endfor %}
</ul>
<p align="center">{{ footer }}</p>
</body>
</html>"""

    author_tmpl = JINJA_ENV.from_string(author_tmpl_html)
    author_index_rows = []

    for idx, (author_name, author_reviews) in enumerate(
            sorted(by_author.items(), key=lambda x: x[0].lower())):
        a_slug = author_slug(author_name, idx)
        author_reviews_sorted = sorted(author_reviews, key=lambda x: x['date_str'], reverse=True)
        dst_auth = SITE / 'review' / 'author' / a_slug / 'index.html'
        dst_auth.parent.mkdir(parents=True, exist_ok=True)
        dst_auth.write_text(author_tmpl.render(
            author=author_name,
            reviews=author_reviews_sorted,
            footer=FOOTER,
        ), encoding='utf-8')
        author_index_rows.append({
            'name': author_name,
            'slug': a_slug,
            'count': len(author_reviews),
        })

    # Author index
    author_index_html = """<!DOCTYPE html>
<html>
<head>
  <title>Blues.Ru: авторы обзоров</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <link rel="shortcut icon" href="/images/bluesru.ico">
  <style>body { max-width: 900px; margin: 0 auto; padding: 0 1em; }</style>
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc" alink="#00bb00">
<p><a href="/"><b>Blues.Ru</b></a> &gt; <a href="/review/">CD обзор</a></p>
<h2>Авторы обзоров</h2>
<ul>
{% for a in authors %}
<li><a href="/review/author/{{ a.slug }}/">{{ a.name | e }}</a> ({{ a.count }})</li>
{% endfor %}
</ul>
<p align="center">{{ footer }}</p>
</body>
</html>"""
    ai_tmpl = JINJA_ENV.from_string(author_index_html)
    (SITE / 'review' / 'author' / 'index.html').write_text(
        ai_tmpl.render(authors=author_index_rows, footer=FOOTER), encoding='utf-8')

    # ── /artist/various-musicians/ stub page ────────────────────────────────
    various_reviews = []
    for meta, body in reviews:
        album_id = str(meta.get('album_id', ''))
        album = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or meta.get('artist_id', '') or '')
        artist = artists.get(artist_id, {})
        if artist_slug_for_url(artist) == 'various-musicians':
            album_slug = album.get('slug', '') or meta.get('slug', '')
            various_reviews.append({
                'url': f'/artist/various-musicians/{_strip_artist_prefix("various-musicians", album_slug)}/',
                'album_title': album.get('title') or meta.get('album') or '',
                'year': album.get('year', ''),
                'asin': album.get('asin', ''),
                'cover_url': cover_url_for_asin(album.get('asin', '')),
            })

    if various_reviews:
        various_html = """<!DOCTYPE html>
<html>
<head>
  <title>Blues.Ru: Разные артисты</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <link rel="shortcut icon" href="/images/bluesru.ico">
  <style>body { max-width: 900px; margin: 0 auto; padding: 0 1em; }</style>
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc" alink="#00bb00">
<h2><a href="/artist/">Музыканты</a> : Разные артисты</h2>
<ul>
{% for r in reviews %}
<li>
  {% if r.cover_url %}<a href="{{ r.url }}"><img src="{{ r.cover_url }}" alt="" border="0" style="vertical-align:middle;margin-right:4px;" width="40" height="40"></a>{% endif %}
  <a href="{{ r.url }}"><b>{{ r.album_title | e }}</b></a>{% if r.year %}, {{ r.year }}{% endif %}
</li>
{% endfor %}
</ul>
<p align="center">{{ footer }}</p>
</body>
</html>"""
        v_tmpl = JINJA_ENV.from_string(various_html)
        dst_v = SITE / 'artist' / 'various-musicians' / 'index.html'
        dst_v.parent.mkdir(parents=True, exist_ok=True)
        dst_v.write_text(v_tmpl.render(reviews=various_reviews, footer=FOOTER), encoding='utf-8')

    print(f"  Reviews: {generated} pages, {len(month_keys)} month indexes, {len(by_author)} author pages")


def generate_news():
    print("Generating news pages...")
    items = []
    for year_dir in sorted(NEWS_DIR.iterdir()):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for nf in sorted(month_dir.glob('*.md')):
                m = RE_FM.match(nf.read_text(encoding='utf-8'))
                if m:
                    meta = yaml.safe_load(m.group(1))
                    body = m.group(2).strip()
                    items.append((meta, body))

    items.sort(key=lambda x: str(x[0].get('date', '0000')), reverse=True)

    tmpl = JINJA_ENV.get_template('news_list.html.j2')

    def fmt_date(date_str):
        try:
            dt = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return str(date_str) if date_str else ''

    def format_news_body(body):
        """Normalize paragraph breaks in news body HTML.

        Bodies may already contain <p>...</p> tags, or use bare double newlines
        as paragraph separators, or a mix of both. Always wraps in <p> tags.
        """
        body = body.strip()
        if not body:
            return body
        # Normalize existing </p> whitespace <p> sequences
        body = re.sub(r'</p>\s*\n+\s*<p>', '</p><p>', body, flags=re.IGNORECASE)
        if '\n\n' in body:
            parts = re.split(r'\n{2,}', body)
            joined = []
            for i, part in enumerate(parts):
                part = part.strip()
                if not part:
                    continue
                if i > 0 and joined:
                    prev = joined[-1]
                    # Only add </p><p> if prev doesn't end with </p> and part doesn't start with <p>
                    prev_lower = prev.lower().rstrip()
                    part_lower = part.lower()
                    if prev_lower.endswith('</p>') or part_lower.startswith('<p>'):
                        joined.append(part)
                    else:
                        joined[-1] = prev + '</p><p>' + part
                        continue
                joined.append(part)
            body = '\n'.join(joined)
        # Ensure single-paragraph bodies are wrapped
        body_lower = body.lower()
        if not (body_lower.startswith('<p>') and body_lower.rstrip().endswith('</p>')):
            body = f'<p>{body}</p>'
        return body

    def make_news_item(meta, body):
        date_str = str(meta.get('date', ''))
        nid = meta.get('id', '')
        slug = meta.get('slug', f'story{nid}')
        url = (f'/news/{date_str[:4]}/{date_str[5:7]}/{date_str[8:10]}/story{nid}/'
               if date_str else '#')
        return {
            'id': nid,
            'slug': slug,
            'title': meta.get('title', ''),
            'date_display': fmt_date(date_str),
            'date_str': date_str,
            'body': format_news_body(body),
            'author': meta.get('author', '') or '',
            'source': meta.get('source', '') or '',
            'url': url,
            'image_path': None,
        }

    all_items = [make_news_item(meta, body) for meta, body in items]

    # ── 1. /news/ — 10 latest ──────────────────────────────────────────────────
    # Build month index first (needed for nav links)
    from collections import defaultdict
    by_month = defaultdict(list)
    for item in all_items:
        ds = item['date_str']
        if ds and len(ds) >= 7:
            by_month[ds[:7]].append(item)
    month_keys_sorted = sorted(by_month.keys(), reverse=True)  # newest first

    # Nav: link to the 6 most recent months + archive link
    def month_label(k):
        y2, m2 = k[:4], int(k[5:7])
        return f'<a href="/news/{y2}/{m2:02d}/">{y2} {MONTHS_RU[m2]}</a>'
    recent_links = ' | '.join(month_label(k) for k in month_keys_sorted[:6])
    more_months_html = recent_links + ' | <a href="/news/archive/">Весь архив →</a>'

    # Bottom nav for first page: link to the month of the 11th item (oldest not shown)
    bottom_nav_html = more_months_html
    if len(all_items) > 10:
        next_month_key = all_items[10]['date_str'][:7]
        if len(next_month_key) >= 7:
            y2, m2 = next_month_key[:4], int(next_month_key[5:7])
            bottom_nav_html = (
                f'{month_label(next_month_key)} → | <a href="/news/archive/">Весь архив →</a>'
            )

    dst = SITE / 'news' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(tmpl.render(
        news_items=all_items[:10],
        page_title='Блюзовые новости',
        nav_links=more_months_html,
        bottom_nav=bottom_nav_html,
        footer=FOOTER,
    ), encoding='utf-8')

    # ── 2. /news/YYYY/MM/ — monthly archive pages ──────────────────────────────
    month_keys = sorted(by_month.keys())
    monthly_count = 0
    for i, key in enumerate(month_keys):
        year, mo = key[:4], int(key[5:7])
        prev_key = month_keys[i - 1] if i > 0 else None
        next_key = month_keys[i + 1] if i + 1 < len(month_keys) else None

        def month_nav(k):
            if not k:
                return ''
            y2, m2 = k[:4], int(k[5:7])
            return f'<a href="/news/{y2}/{m2:02d}/">{y2} {MONTHS_RU[m2]}</a>'

        # Backward chronology: newer month on left (←), older on right (→)
        parts = []
        if next_key:  # next_key = newer month (higher in ascending list)
            parts.append(f'← {month_nav(next_key)}')
        parts.append(f'<b>{year} {MONTHS_RU[mo]}</b>')
        if prev_key:  # prev_key = older month (lower in ascending list)
            parts.append(f'{month_nav(prev_key)} →')
        nav = ' | '.join(parts)

        dst_month = SITE / 'news' / year / f'{mo:02d}' / 'index.html'
        dst_month.parent.mkdir(parents=True, exist_ok=True)
        dst_month.write_text(tmpl.render(
            news_items=by_month[key],
            page_title=f'Блюзовые новости: {year} {MONTHS_RU[mo]}',
            nav_links=nav,
            footer=FOOTER,
        ), encoding='utf-8')
        monthly_count += 1

    # ── 3. /news/YYYY/MM/DD/storyN/ — individual story pages ──────────────────
    story_tmpl = JINJA_ENV.get_template('news_list.html.j2')
    story_count = 0
    for item in all_items:
        ds = item['date_str']
        if not ds or len(ds) < 10:
            continue
        year, mo_str, day = ds[:4], ds[5:7], ds[8:10]
        nid = item['id']
        dst_story = SITE / 'news' / year / mo_str / day / f'story{nid}' / 'index.html'
        dst_story.parent.mkdir(parents=True, exist_ok=True)

        mo_int = int(mo_str)
        back_nav = (f'← <a href="/news/{year}/{mo_str}/">{year} {MONTHS_RU[mo_int]}</a>'
                    f'  |  <a href="/news/">Все новости</a>')

        dst_story.write_text(story_tmpl.render(
            news_items=[item],
            page_title=item['title'],
            nav_links=back_nav,
            footer=FOOTER,
        ), encoding='utf-8')
        story_count += 1

    print(f"  News: {len(all_items)} items, {monthly_count} monthly pages, {story_count} story pages")

    # ── 4. /news/archive/ — full month archive ────────────────────────────────
    # Build year → list of {key, label, count} newest first
    from collections import OrderedDict as _OD
    years_arch = _OD()
    for mk in month_keys_sorted:
        yr = mk[:4]
        y2, m2 = mk[:4], int(mk[5:7])
        years_arch.setdefault(yr, []).append({
            'key': mk,
            'label': f'{y2} {MONTHS_RU[m2]}',
            'url': f'/news/{y2}/{m2:02d}/',
            'count': len(by_month[mk]),
        })

    archive_html_parts = []
    for yr, months in years_arch.items():
        links = ' | '.join(
            f'<a href="{m["url"]}">{MONTHS_RU[int(m["key"][5:7])]} ({m["count"]})</a>'
            for m in months
        )
        archive_html_parts.append(f'<h3>{yr}</h3><p>{links}</p>')

    arch_body = '\n'.join(archive_html_parts)
    archive_page = f"""\
<!DOCTYPE html>
<html>
<head>
<title>Архив Блюзовых новостей — Blues.Ru</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<link rel="shortcut icon" href="/images/bluesru.ico">
<link rel="stylesheet" href="/static/css/site.css">
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc">
<h2>Архив Блюзовых новостей</h2>
<p><a href="/news/">← Последние новости</a></p>
{arch_body}
<hr size="1">
<p align="center">{FOOTER}</p>
</body>
</html>"""
    arch_dst = SITE / 'news' / 'archive' / 'index.html'
    arch_dst.parent.mkdir(parents=True, exist_ok=True)
    arch_dst.write_text(archive_page, encoding='utf-8')


def generate_updates():
    """Generate /updates/ section from bluesru/announcements/ YAML.

    URL structure:
      /updates/          — most recent full year with <h2>YEAR</h2>, link to next year
      /updates/YYYY/     — full year, reverse chrono, top/bottom nav with year list
    """
    print("Generating updates pages...")
    if not ANNOUNCE_DIR.exists():
        print("  ANNOUNCE_DIR not found, skipping updates")
        return

    _atb_re = re.compile(
        r'\bATB\b|atb_|/[Aa]tb/|Весь\s+[Ээ]тот\s+[Бб]люз|All\s+That\s+Blues',
        re.IGNORECASE)

    items = []
    atb_skipped = 0
    for p in sorted(ANNOUNCE_DIR.glob('*.md')):
        text = p.read_text(encoding='utf-8')
        if _atb_re.search(text):
            atb_skipped += 1
            continue
        m = RE_FM.match(text)
        if m:
            meta = yaml.safe_load(m.group(1))
            body = m.group(2).strip()
            items.append((meta, body))

    items.sort(key=lambda x: str(x[0].get('date', '0000')), reverse=True)

    tmpl = JINJA_ENV.get_template('updates_list.html.j2')

    def fmt_date(date_str):
        try:
            dt = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return str(date_str) if date_str else ''

    def make_item(meta, body):
        date_str = str(meta.get('date', ''))
        nid = str(meta.get('id', ''))
        year = date_str[:4] if date_str else ''
        return {
            'id': nid,
            'date_display': fmt_date(date_str),
            'date_str': date_str,
            'body': format_news_body_simple(body),
        }

    all_items = [make_item(meta, body) for meta, body in items]

    from collections import defaultdict
    by_year = defaultdict(list)
    for item in all_items:
        year = item['date_str'][:4] if item['date_str'] else ''
        if year:
            by_year[year].append(item)
    year_list = sorted(by_year.keys(), reverse=True)

    def year_nav_html(current, prev_y, next_y):
        # year_list is sorted descending: prev_y=older, next_y=newer
        # Backward chronology: newer (←) on left, older (→) on right
        parts = []
        if next_y:  # newer year
            parts.append(f'← <a href="/updates/{next_y}/">{next_y}</a>')
        parts.append(f'<b>{current}</b>')
        if prev_y:  # older year
            parts.append(f'<a href="/updates/{prev_y}/">{prev_y}</a> →')
        return ' | '.join(parts)

    # ── /updates/ — most recent 15 items (may span multiple years) ──────────
    dst = SITE / 'updates' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    recent = all_items[:15]
    # Group the recent items by year for rendering
    from collections import OrderedDict
    recent_by_year = OrderedDict()
    for item in recent:
        y = item['date_str'][:4] if item['date_str'] else ''
        if y not in recent_by_year:
            recent_by_year[y] = []
        recent_by_year[y].append(item)
    recent_year_blocks = [{'year': y, 'entries': entries} for y, entries in recent_by_year.items()]
    # Link to oldest year shown → it has more entries
    oldest_shown = list(recent_by_year.keys())[-1] if recent_by_year else None
    more_years_html = f'<a href="/updates/{oldest_shown}/">{oldest_shown}</a> →' if oldest_shown else ''

    dst.write_text(tmpl.render(
        page_title='Обновления Blues.Ru',
        current_year=None,
        nav_links=None,
        year_blocks=recent_year_blocks,
        more_years=more_years_html,
        year_list=year_list,
        footer=FOOTER,
    ), encoding='utf-8')

    # ── /updates/YYYY/ — per-year pages ───────────────────────────────────────
    for i, year in enumerate(year_list):
        prev_y = year_list[i + 1] if i + 1 < len(year_list) else None
        next_y = year_list[i - 1] if i > 0 else None
        nav = year_nav_html(year, prev_y, next_y)

        dst_year = SITE / 'updates' / year / 'index.html'
        dst_year.parent.mkdir(parents=True, exist_ok=True)
        dst_year.write_text(tmpl.render(
            page_title=f'Обновления Blues.Ru: {year}',
            current_year=year,
            nav_links=nav,
            year_blocks=[{'year': year, 'entries': by_year[year]}],
            more_years=None,
            year_list=year_list,
            footer=FOOTER,
        ), encoding='utf-8')

    print(f"  Updates: {len(all_items)} items, {len(year_list)} year pages (filtered {atb_skipped} ATB)")


def format_news_body_simple(body):
    """Format announcements body: split on double newlines → paragraphs.
    Single newlines are left as whitespace (not converted to <br>).
    Bodies that already have <p> tags are returned as-is."""
    body = body.strip()
    if not body:
        return body
    # Already has block-level HTML — normalize spacing between tags and return
    if re.search(r'<p[\s>]', body, re.IGNORECASE):
        body = re.sub(r'</p>\s*\n+\s*<p>', '</p><p>', body, flags=re.IGNORECASE)
        return body
    # Split on double (or more) newlines → separate paragraphs
    if '\n\n' in body:
        parts = re.split(r'\n{2,}', body)
        result = []
        for part in parts:
            part = part.strip()
            if part:
                result.append('<p>' + part + '</p>')
        return '\n'.join(result)
    # Single block — wrap in one paragraph (single newlines become spaces)
    return '<p>' + body + '</p>'


def _load_artist_reviews():
    """Return dict: artist_id → list of (meta, body) for reviews with that artist."""
    reviews, _ = load_reviews()
    albums = load_albums()
    by_artist = {}
    for meta, body in reviews:
        album_id = str(meta.get('album_id', ''))
        album = albums.get(album_id, {})
        artist_id = str(album.get('artist_id', '') or '')
        if artist_id:
            by_artist.setdefault(artist_id, []).append((meta, body))
    return by_artist


def _generate_stub_artist_page(artist, reviews_list, albums):
    """Generate a stub page for an artist with reviews but no static bio."""
    import html as html_mod2

    def _fmt_mark(mark):
        n = int(mark)
        return '@' * (n // 2) + ('+' if n % 2 else '')

    slug = artist.get('slug', '')
    name = artist.get('name', '')
    amg_id = artist.get('amg_id', '')

    reviews_data = []
    for meta, body in sorted(reviews_list, key=lambda x: -int(x[0].get('id', 0))):
        album_id = str(meta.get('album_id', ''))
        album = albums.get(album_id, {})
        mark = meta.get('mark')
        reviews_data.append({
            'id': meta.get('id', ''),
            'album_title': album.get('title', '') or meta.get('album', ''),
            'year': album.get('year', ''),
            'author': meta.get('author', ''),
            'body': format_review_body(body),
            'mark': mark,
            'mark_text': _fmt_mark(mark) if mark else '',
        })

    tmpl = JINJA_ENV.get_template('albumview.html.j2')
    # Use first album for the page
    first_meta = reviews_list[0][0] if reviews_list else {}
    album_id = str(first_meta.get('album_id', ''))
    album = albums.get(album_id, {})

    out = tmpl.render(
        album={'title': '', 'artist': name, 'year': '', 'label': '', 'asin': '', 'amg_id': amg_id},
        cover_url='',
        artist_name=name,
        artist_legacy_path='',  # no legacy dir — this IS the landing page
        reviews=reviews_data,
        streaming_links='',
        artist_streaming_links=streaming_links_html(slug, kind='artist'),
        footer=FOOTER,
    )

    dst = SITE / 'artist' / slug / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding='utf-8')
    return dst


def generate_bluesmen():
    print("Generating bluesmen pages...")
    artists = load_artists()
    tmpl = JINJA_ENV.get_template('bluesmen_list.html.j2')
    resources_by_artist = load_resources()

    # Prefer content/ (populated by populate.py); fall back to original blues-ru/
    _content_bluesmen = CONTENT / 'artist'
    SRC_BLUESMEN = _content_bluesmen if _content_bluesmen.exists() and any(_content_bluesmen.iterdir()) else BLUES_RU / 'bluesmen'
    print(f"  Source: {SRC_BLUESMEN}")

    # Load reviews grouped by artist_id
    artist_reviews = _load_artist_reviews()
    albums = load_albums()

    # Build letter index
    from collections import defaultdict
    by_letter = defaultdict(list)
    letters_all = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    letter_has = {l: False for l in letters_all}

    bio_count = 0
    stub_count = 0

    for a in artists:
        name = a.get('name', '')
        sort_name = a.get('sort_name', name) or name
        # Primary entry: group by first letter of display name.
        # "Stevie Ray Vaughan" → S.
        letter = name[0].upper() if name else '#'
        if letter not in letter_has:
            letter = '#'

        lp = a.get('legacy_path', '').strip('/')
        parts = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        external = '.' in legacy_dir or legacy_dir.startswith('www.')
        if external:
            legacy_dir = ''

        src_dir = SRC_BLUESMEN / legacy_dir if legacy_dir else None
        has_dir = src_dir and src_dir.exists()
        # Fallback: if DB legacy_dir doesn't exist, try name-based directory guess
        if not has_dir and legacy_dir:
            name_dir = name.replace(' ', '_') if name else ''
            name_src = SRC_BLUESMEN / name_dir if name_dir else None
            if name_src and name_src.exists():
                src_dir = name_src
                has_dir = True
                legacy_dir = name_dir  # use actual dir name for URL

        artist_id = str(a.get('id', ''))
        has_reviews = bool(artist_reviews.get(artist_id))

        # Determine what URL to link
        # DB artists always use slug (lowercase-dashes); orphans use legacy_dir
        slug = a.get('slug', '')
        if has_dir and slug:
            link_dir = slug   # bio page at /artist/{slug}/
        elif has_dir:
            link_dir = legacy_dir  # orphan fallback: dir name as-is
        elif has_reviews and slug:
            link_dir = slug  # stub page at /artist/{slug}/
        else:
            link_dir = ''

        # Build resource links for list display (links to bio sub-pages)
        artist_resources = resources_by_artist.get(artist_id, [])
        list_res_slug = link_dir if link_dir else slug
        resource_links = _build_resource_links(artist_resources, list_res_slug) if artist_resources else ''
        # Append streaming links
        stream_html = streaming_links_html(slug, kind='artist')
        if stream_html:
            resource_links = (resource_links + ' | ' if resource_links else '') + stream_html

        row = {
            'id': artist_id,
            'name': name,
            'sort_name': sort_name,
            'letter': letter,
            'legacy_dir': link_dir,
            'external': external,
            'amg_id': a.get('amg_id', ''),
            'slug': slug,
            'secondary': False,
            'resource_links': resource_links,
        }
        by_letter[letter].append(row)
        if link_dir:
            letter_has[letter] = True

        # Secondary (cross-reference) entry under first letter of sort_name surname.
        # "Vaughan, Stevie Ray" → V, with a back-link to the primary entry.
        if sort_name != name and slug:
            sort_letter = sort_name[0].upper()
            if sort_letter not in letter_has:
                sort_letter = '#'
            if sort_letter != letter:  # avoid duplicate entry under same letter
                sec_row = {
                    'id': artist_id,
                    'name': name,
                    'sort_name': sort_name,
                    'letter': sort_letter,
                    'legacy_dir': link_dir,
                    'external': external,
                    'amg_id': '',
                    'slug': slug,
                    'secondary': True,  # renders as "Sort, Name → link to primary"
                    'resource_links': '',
                }
                by_letter[sort_letter].append(sec_row)
                if link_dir:
                    letter_has[sort_letter] = True

        # Process artist bio pages (from static source)
        if has_dir:
            _process_artist_dir(a, src_dir, SRC_BLUESMEN,
                                artist_resources=resources_by_artist.get(artist_id))
            bio_count += 1
        elif has_reviews and slug:
            # Generate stub page with review list
            _generate_stub_artist_page(a, artist_reviews[artist_id], albums)
            stub_count += 1

    # Fallback pass: process any bio dirs in SRC_BLUESMEN not yet handled
    # (orphaned dirs: no DB legacy_path or DB legacy_path points to wrong name)
    processed_dirs = set()
    for a in artists:
        lp = a.get('legacy_path', '').strip('/')
        parts = lp.split('/')
        legacy_dir = parts[-1] if (parts and parts[-1]) else ''
        if legacy_dir and '.' not in legacy_dir and not legacy_dir.startswith('www.'):
            processed_dirs.add(legacy_dir)
        # Also track name-based fallback dir (e.g. Luther_Allison vs Allison_Luther)
        name = a.get('name', '')
        if name and legacy_dir and '.' not in legacy_dir:
            name_dir = name.replace(' ', '_')
            if (SRC_BLUESMEN / name_dir).exists():
                processed_dirs.add(name_dir)

    orphan_count = 0
    for src_dir in sorted(SRC_BLUESMEN.iterdir()):
        if not src_dir.is_dir():
            continue
        if src_dir.name in processed_dirs:
            continue
        # This directory was not claimed by any DB artist — process as orphan
        dir_name = src_dir.name
        # Infer artist name from directory name (underscores → spaces)
        inferred_name = dir_name.replace('_', ' ')
        # For orphans without DB sort_name, use inferred_name for grouping
        letter = inferred_name[0].upper() if inferred_name else '#'
        if letter not in letter_has:
            letter = '#'
        # Build a minimal artist dict (no DB id/slug/reviews)
        orphan_artist = {
            'id': '',
            'slug': '',
            'name': inferred_name,
            'sort_name': inferred_name,
            'legacy_path': f'/artist/{dir_name}/',
            'amg_id': '',
        }
        _process_artist_dir(orphan_artist, src_dir, SRC_BLUESMEN)
        bio_count += 1
        orphan_count += 1
        row = {
            'id': '',
            'name': inferred_name,
            'sort_name': inferred_name,
            'letter': letter,
            'legacy_dir': dir_name,
            'external': False,
            'amg_id': '',
            'slug': '',
            'secondary': False,
            'resource_links': '',
        }
        by_letter[letter].append(row)
        if dir_name:
            letter_has[letter] = True

    if orphan_count:
        print(f"  Orphan bio dirs processed: {orphan_count}")

    # Add "Various Musicians" entry under V if there are compilation reviews
    various_page = SITE / 'artist' / 'various-musicians' / 'index.html'
    if various_page.exists():
        by_letter['V'].append({
            'id': '',
            'name': 'Various Musicians',
            'sort_name': 'Various Musicians',
            'letter': 'V',
            'legacy_dir': 'various-musicians',
            'external': False,
            'amg_id': '',
            'slug': 'various-musicians',
            'secondary': False,
            'resource_links': '',
        })
        letter_has['V'] = True

    letters_used = [l for l in letters_all if l in by_letter]
    for l in by_letter:
        # Sort within each letter group:
        # — secondary (sort_name cross-refs) sort by sort_name
        # — primary entries sort by name
        # — secondaries go after primaries with the same first letter
        by_letter[l].sort(key=lambda x: (x['secondary'], x['sort_name'].lower() if x['secondary'] else x['name'].lower()))

    out = tmpl.render(
        letters=letters_used,
        letter_has_artists=letter_has,
        artists_by_letter=by_letter,
    )
    dst = SITE / 'artist' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding='utf-8')
    print(f"  Bluesmen list: {len(artists)} artists, {bio_count} bio pages + {stub_count} stub pages")


def _find_main_htm(src_dir):
    """Return the main .htm file for an artist directory (the one to rename to index.html)."""
    dir_name = src_dir.name
    skip_sfx = ['_lyr', '_tab', '_lyric', '_lyrics', '_tabs']
    htm_files = [
        f for f in sorted(src_dir.iterdir())
        if f.suffix.lower() in ('.htm', '.html')
        and f.name.lower() not in ('default.htm', 'default.html')
        and not any(f.stem.lower().endswith(s) for s in skip_sfx)
    ]
    if not htm_files:
        return None
    # Prefer file whose stem matches directory name (case-insensitive)
    dir_lower = dir_name.lower()
    for f in htm_files:
        if f.stem.lower() == dir_lower:
            return f
    # Fall back to first non-skip file
    return htm_files[0]


def _process_artist_dir(artist, src_dir, src_root, artist_resources=None):
    """Post-process all files in an artist dir to site/artist/{slug}/"""
    slug = artist.get('slug', '')
    legacy_dir = src_dir.name
    # Use slug-based path if available; fall back to legacy_dir for orphans
    url_dir = slug if slug else legacy_dir
    dst_dir = SITE / 'artist' / url_dir
    dst_dir.mkdir(parents=True, exist_ok=True)

    for src_path in sorted(src_dir.rglob('*')):
        if not src_path.is_file():
            continue
        ext = src_path.suffix.lower()
        if ext in SKIP_EXTENSIONS:
            continue
        if src_path.name.lower() in {'config.xml'}:
            continue

        rel = src_path.relative_to(src_dir)
        parts = rel.parts
        out_name = _normalize_filename(src_path.name)
        # The main artist HTM file (e.g. Alex_Schultz.htm) becomes index.html
        # so that /artist/albert-collins/ serves it directly.
        main_htm = _find_main_htm(src_dir)
        is_main_rename = (len(parts) == 1 and main_htm and src_path == main_htm)
        if is_main_rename:
            out_name = 'index.html'
        if len(parts) > 1:
            dst_path = dst_dir / Path(*parts[:-1]) / out_name
        else:
            dst_path = dst_dir / out_name
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if ext in ('.htm', '.html'):
            content = read_file(src_path)
            if content:
                is_main = (main_htm and src_path == main_htm)
                content = process_html(
                    content, src_path.parent, src_root,
                    artist_slug=slug if is_main else None,
                    artist_name=artist.get('name', '') if is_main else None,
                    artist_legacy_dir=url_dir if is_main else None,
                    artist_resources=artist_resources if is_main else None,
                )
                dst_path.write_text(content, encoding='utf-8')
                # Also write at original filename (if it was renamed to index.html)
                # so /artist/albert-collins/Alex_Schultz.htm remains accessible
                if is_main_rename and src_path.name.lower() not in ('default.htm', 'default.html', 'index.htm', 'index.html'):
                    orig_dst = dst_dir / _normalize_filename(src_path.name)
                    if orig_dst != dst_path:
                        orig_dst.write_text(content, encoding='utf-8')
                continue
        shutil.copy2(src_path, dst_path)


def _gallery_dir_prefixes():
    """
    Return a set of site-relative path prefixes for lightroom/mts gallery directories.
    Any .htm/.html file whose site-relative path starts with one of these prefixes
    should be skipped — these are per-photo Lightroom-generated pages.
    Custom galleries are NOT included: their HTM files are real content pages that
    should be copied to site/ as-is.
    Prefixes use forward slashes and end with '/'.
    Also includes parent paths for galleries ending in '/content' (Lightroom exports).
    """
    if not GALLERIES_YAML.exists():
        return set()
    galleries = yaml.safe_load(GALLERIES_YAML.read_text(encoding='utf-8')) or []
    prefixes = set()
    for g in galleries:
        gpath = g.get('path', '')
        gtype = g.get('type', '')
        if not gpath or gtype == 'custom':
            continue  # custom galleries have real content HTMs, don't skip them
        prefixes.add(f"bluesnews/{gpath}/")
        if gpath.endswith('/content'):
            prefixes.add(f"bluesnews/{gpath[:-8]}/")
    return prefixes


def _build_custom_gallery_media_map():
    """
    Return a dict mapping bluesnews/ path prefix → absolute media base URL
    for all custom-type galleries. Used to rewrite img src in their HTML pages.
    e.g. "bluesnews/00Autumn/" → "https://media.blues.ru/photo/2000/2000-10-efes-blues-festival"
    """
    if not GALLERIES_YAML.exists():
        return {}
    galleries = yaml.safe_load(GALLERIES_YAML.read_text(encoding='utf-8')) or []
    result = {}
    for g in galleries:
        gpath = g.get('path', '')
        gtype = g.get('type', '')
        if not gpath or gtype != 'custom':
            continue
        yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')
        per_yaml = GALLERIES_DIR / f"{yaml_slug}.yaml"
        data = {}
        if per_yaml.exists():
            data = yaml.safe_load(per_yaml.read_text(encoding='utf-8')) or {}
        if data.get('exclude'):
            continue
        canonical_rel, _ = _gallery_canonical_url(data, gpath)
        prefix = f"bluesnews/{gpath}/"
        result[prefix] = f"{MEDIA_BASE_URL}/{canonical_rel}"
    return result


def _rewrite_gallery_img_src(html_content, media_base_url):
    """
    Rewrite relative <img src="..."> and <a href="..."> for image files
    in a custom gallery page to use absolute media.blues.ru URLs.
    Only rewrites relative paths (not already-absolute URLs).
    """
    img_exts = r'(?i)\.(jpg|jpeg|png|gif|bmp|webp)'

    def rewrite_attr(m):
        attr = m.group(1)   # 'src' or 'href'
        quote = m.group(2)  # '"' or "'"
        val = m.group(3)
        # Skip absolute URLs and anchors
        if val.startswith(('http://', 'https://', '/', '#', 'mailto:', 'javascript:')):
            return m.group(0)
        # Only rewrite image file refs
        if re.search(img_exts, val.split('?')[0].split('#')[0]):
            # Strip leading ./
            clean = val.lstrip('./')
            return f'{attr}={quote}{media_base_url}/{clean}{quote}'
        return m.group(0)

    pattern = re.compile(r'(src|href)=(["\'])([^"\']+)\2', re.IGNORECASE)
    return pattern.sub(rewrite_attr, html_content)


def _gallery_canonical_url(data, gpath):
    """
    Return (canonical_url, year_str) for a gallery.
    canonical_url is like /photo/2004/2004-10-efes-blues-festival-2004/ (no leading /).
    """
    canonical_date = data.get('canonical_date') or ''
    gallery_slug = data.get('slug') or re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')

    # Extract year from canonical_date
    m = re.match(r'^(\d{4})', str(canonical_date))
    if m:
        year_str = m.group(1)
    else:
        year = _gallery_year(gpath)
        year_str = str(year) if year else 'misc'

    # Build date prefix for the directory name
    # canonical_date may be YYYY, YYYY-MM, or YYYY-MM-DD
    cd = str(canonical_date)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', cd):
        date_prefix = cd          # full date
    elif re.match(r'^\d{4}-\d{2}$', cd):
        date_prefix = cd          # year-month
    elif re.match(r'^\d{4}$', cd):
        date_prefix = cd          # year only
    else:
        date_prefix = year_str

    # Strip trailing year/date suffix from slug to avoid "2000-10-efes-2000" duplication.
    # Slugs often include the year for readability; when we prepend the date prefix it repeats.
    clean_slug = gallery_slug
    # Strip trailing -YYYY or -YYYY-MM-DD
    clean_slug = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', clean_slug).rstrip('-')
    clean_slug = re.sub(r'-\d{4}-\d{2}$', '', clean_slug).rstrip('-')
    clean_slug = re.sub(r'-\d{4}$', '', clean_slug).rstrip('-')
    if not clean_slug:
        clean_slug = gallery_slug  # fallback if slug was only the date

    # Avoid duplicating the date prefix if the slug already starts with it
    if gallery_slug.startswith(date_prefix):
        dir_name = gallery_slug
    else:
        dir_name = f"{date_prefix}-{clean_slug}"
    return f"photo/{year_str}/{dir_name}", year_str


def generate_galleries():
    """Generate gallery index pages from extracted-data/galleries/ YAML.

    Canonical URL: /photo/YYYY/YYYY-MM-DD-slug/
    Legacy URL /bluesnews/{path}/ gets a 301 redirect (written to _redirects).
    """
    if not GALLERIES_YAML.exists():
        print("  No galleries.yaml found, skipping.")
        return

    galleries = yaml.safe_load(GALLERIES_YAML.read_text(encoding='utf-8')) or []
    tmpl = JINJA_ENV.get_template('gallery.html.j2')
    count = 0
    redirects = []  # list of (old_path, new_path) for _redirects

    for g in galleries:
        gpath = g.get('path', '')
        yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')
        per_yaml = GALLERIES_DIR / f"{yaml_slug}.yaml"
        if not per_yaml.exists():
            continue
        data = yaml.safe_load(per_yaml.read_text(encoding='utf-8')) or {}
        if data.get('exclude'):
            continue  # Explicitly excluded gallery
        photos = [p for p in (data.get('photos') or []) if isinstance(p, dict) and p.get('file')]

        # For galleries indexed as {parent}/content, output at the parent level.
        # The content/ subdir is just a Lightroom export artifact; the canonical URL is parent/.
        # Prefix photo paths with 'content/' to keep image URLs correct.
        legacy_path = gpath
        if gpath.endswith('/content'):
            legacy_path = gpath[:-8]  # strip '/content'
            photos = [dict(p, file='content/' + p['file']) for p in photos]

        # Canonical URL path (relative to site/)
        canonical_rel, year_str = _gallery_canonical_url(data, gpath)

        # Media base for this gallery: absolute URL prefix for all images
        gallery_media_base = f"{MEDIA_BASE_URL}/{canonical_rel}"

        # Build photo list with absolute media URLs
        def _abs_url(rel_file):
            return f"{gallery_media_base}/{rel_file}"

        photos_with_media = [
            dict(p, file=_abs_url(p['file']),
                 thumb=_abs_url(p.get('thumb') or p['file']))
            for p in photos if p.get('file')
        ]

        # Build JSON-safe photo list for the lightbox script
        photos_json = json.dumps(
            [{'file': _abs_url(p['file']), 'caption': p.get('caption') or '',
              'thumb': _abs_url(p.get('thumb') or p['file'])}
             for p in photos if p.get('file')],
            ensure_ascii=False)

        clean_title = data.get('clean_title') or data.get('title') or legacy_path
        canonical_date = data.get('canonical_date') or data.get('date') or ''
        description = data.get('description') or ''
        # Only show extra_text if it's short (not an article) AND no description
        extra_text = data.get('extra_text') or ''
        if len(extra_text) > 500:
            extra_text = ''  # long articles belong on their source pages

        html = tmpl.render(
            path=legacy_path,
            canonical_url='/' + canonical_rel + '/',
            title=clean_title,
            date=canonical_date,
            description=description,
            extra_text=extra_text if not description else '',
            photo_count=data.get('photo_count', len(photos)),
            photos=photos_with_media,
            photos_json=photos_json,
            year=year_str,
            source_articles=data.get('source_articles') or [],
            footer=FOOTER,
        )

        out_dir = SITE / canonical_rel
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'index.html').write_text(html, encoding='utf-8')
        count += 1

        # Record redirect: /bluesnews/{legacy_path}/ → /photo/.../ (301)
        old_url = f"/bluesnews/{legacy_path}/"
        new_url = f"/{canonical_rel}/"
        if old_url != new_url:
            redirects.append((old_url, new_url))

        # Copy gallery images to media-blues-ru/photo/{canonical_rel}/ (not to SITE).
        # Falls back to source bluesnews/ if not in content/.
        src_bluesnews = BLUESNEWS
        for photo in photos:
            for field in ('file', 'thumb'):
                rel_file = photo.get(field)
                if not rel_file:
                    continue
                dst_img = MEDIA_DIR / canonical_rel / rel_file
                if dst_img.exists():
                    continue
                # Try content/ first (encoding-corrected), then raw bluesnews/ source
                arc_img = CONTENT / 'bluesnews' / legacy_path / rel_file
                if arc_img.exists():
                    dst_img.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(arc_img, dst_img)
                    continue
                if gpath.endswith('/content'):
                    src_img = src_bluesnews / legacy_path / 'content' / rel_file.removeprefix('content/')
                else:
                    src_img = src_bluesnews / legacy_path / rel_file
                if src_img.exists():
                    dst_img.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_img, dst_img)

    # Write gallery redirects to _redirects (append section)
    _write_gallery_redirects(redirects)

    print(f"  galleries: {count} index pages written → site/photo/YYYY/*/index.html")
    print(f"  gallery redirects: {len(redirects)} → bluesru-arc/_redirects")


def _write_gallery_redirects(redirects):
    """Append gallery 301 redirects to bluesru-arc/_redirects."""
    redirects_file = ARC / '_redirects'
    if not redirects_file.exists():
        return

    content = redirects_file.read_text(encoding='utf-8')

    # Remove old gallery redirect block if present
    marker_start = '# BEGIN gallery-redirects'
    marker_end = '# END gallery-redirects'
    if marker_start in content:
        start = content.index(marker_start)
        end = content.index(marker_end) + len(marker_end)
        content = content[:start].rstrip() + '\n' + content[end:].lstrip('\n')

    # Build new block
    lines = [marker_start]
    for old, new in redirects:
        lines.append(f"{old}  {new}  301")
    lines.append(marker_end)

    content = content.rstrip('\n') + '\n\n' + '\n'.join(lines) + '\n'
    redirects_file.write_text(content, encoding='utf-8')


def _gallery_year(path):
    """Extract a 4-digit year from a gallery top-level path component."""
    top = path.split('/')[0].lstrip('_')
    # 4-digit year: 1999-2029
    m = re.search(r'((?:19|20)\d\d)', top)
    if m:
        return int(m.group(1))
    # 2-digit suffix (e.g. Kav16, FedorOchakovo03)
    m = re.search(r'(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    # 2-digit prefix followed by letters (e.g. 04Spring, 09Winter, _12A)
    # Must be followed by non-digit to avoid treating "50Belov" as year 1950
    m = re.match(r'^(\d\d)[^0-9]', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    # Pure 2-digit path (e.g. _13, _14, _22)
    m = re.match(r'^(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    return None


# Extra photo cards added by generators (e.g. NBF) that don't use gallery YAML
_EXTRA_PHOTO_CARDS = []


def generate_photo_index():
    """Generate /photo/index.html — master gallery index organized by year."""
    if not GALLERIES_YAML.exists():
        print("  No galleries.yaml, skipping photo index.")
        return

    galleries = yaml.safe_load(GALLERIES_YAML.read_text(encoding='utf-8')) or []

    cards = []
    for g in galleries:
        gpath = g.get('path', '')
        if not gpath:
            continue

        # Load per-gallery YAML for enriched metadata
        yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')
        per_yaml = GALLERIES_DIR / f"{yaml_slug}.yaml"
        data = {}
        if per_yaml.exists():
            data = yaml.safe_load(per_yaml.read_text(encoding='utf-8')) or {}
        if data.get('exclude'):
            continue  # Explicitly excluded gallery

        canonical_rel, year_str = _gallery_canonical_url(data, gpath)

        # Load first photo for thumbnail
        thumb = ''
        photos = [p for p in (data.get('photos') or []) if isinstance(p, dict) and p.get('file')]
        if photos:
            first_photo = photos[0]
            # Use large image as cover (thumbs are often too small and upscale badly)
            thumb = first_photo.get('file') or first_photo.get('thumb') or ''
            # For /content galleries, images are stored under content/ subdir.
            # generate_galleries() prefixes file paths with 'content/', but the raw YAML
            # does NOT have this prefix — add it here for the index card.
            if gpath.endswith('/content') and thumb and not thumb.startswith('content/'):
                thumb = 'content/' + thumb

        clean_title = data.get('clean_title') or data.get('title') or gpath
        canonical_date = data.get('canonical_date') or data.get('date') or ''

        # Year as integer for grouping
        try:
            year_int = int(year_str) if year_str and year_str != 'misc' else None
        except ValueError:
            year_int = None

        cards.append({
            'path': gpath,
            'canonical_url': '/' + canonical_rel + '/',
            'title': clean_title,
            'date': canonical_date,
            'photo_count': g.get('photo_count', 0),
            'thumb': thumb,
            'year': year_int,
            'year_str': year_str,
        })

    # Include extra cards from other generators (e.g. NBF) by scanning site/photo/
    # Any YYYY/slug/ directory not already covered by YAML cards
    yaml_urls = {c['canonical_url'] for c in cards}
    photo_root = SITE / 'photo'
    if photo_root.exists():
        for year_dir in sorted(photo_root.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            yr_int = int(year_dir.name)
            for gal_dir in sorted(year_dir.iterdir()):
                if not gal_dir.is_dir():
                    continue
                canon_url = f'/photo/{year_dir.name}/{gal_dir.name}/'
                if canon_url in yaml_urls:
                    continue
                idx_html = gal_dir / 'index.html'
                if not idx_html.exists():
                    continue
                # Parse title and photo count from generated HTML
                try:
                    html_text = idx_html.read_text(encoding='utf-8', errors='ignore')
                    m_title = re.search(r'<h1>(.*?)</h1>', html_text)
                    m_count = re.search(r'gallery-count">\s*(\d+)', html_text)
                    title = re.sub(r'<[^>]+>', '', m_title.group(1)) if m_title else gal_dir.name
                    count = int(m_count.group(1)) if m_count else 0
                    # Find first image for thumbnail
                    imgs = re.findall(r'<img src="([^"]+\.jpg)"', html_text)
                    thumb = imgs[0] if imgs else ''
                except Exception:
                    title, count, thumb = gal_dir.name, 0, ''
                cards.append({
                    'path': gal_dir.name,
                    'canonical_url': canon_url,
                    'title': title,
                    'date': year_dir.name,
                    'photo_count': count,
                    'thumb': thumb,
                    'year': yr_int,
                    'year_str': year_dir.name,
                })

    # Group by year
    year_map = {}
    misc = []
    for card in cards:
        y = card['year']
        if y:
            year_map.setdefault(y, []).append(card)
        else:
            misc.append(card)

    years_sorted = sorted(year_map.keys(), reverse=True)
    by_year = [(y, year_map[y]) for y in years_sorted]

    tmpl = JINJA_ENV.get_template('photo_index.html.j2')
    html = tmpl.render(
        years=years_sorted,
        by_year=by_year,
        misc_galleries=misc,
        footer=FOOTER,
    )

    out_dir = SITE / 'photo'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'index.html').write_text(html, encoding='utf-8')
    total = len(cards)
    print(f"  photo index: {total} galleries, {len(years_sorted)} years → site/photo/index.html")

    # ── Clean up stale gallery dirs left over from slug renames ───────────────
    # Build set of valid (year, dirname) pairs from the cards we just rendered
    valid_dirs = set()
    for card in cards:
        url = card.get('canonical_url', '')  # e.g. /photo/2017/2017-01-28-chino-swingslide/
        parts = url.strip('/').split('/')
        if len(parts) >= 3:  # photo / YYYY / dirname
            valid_dirs.add((parts[1], parts[2]))
    # Also keep NBF galleries (generated separately, not in cards)
    stale_removed = 0
    for year_dir in sorted(out_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        for gal_dir in sorted(year_dir.iterdir()):
            if not gal_dir.is_dir():
                continue
            key = (year_dir.name, gal_dir.name)
            if key in valid_dirs:
                continue
            if gal_dir.name.startswith('nbf-'):
                continue  # NBF galleries generated separately
            import shutil
            shutil.rmtree(gal_dir)
            stale_removed += 1
    if stale_removed:
        print(f"  photo index: removed {stale_removed} stale gallery dirs")


def generate_content():
    """
    Copy/post-process static content from bluesru-arc/content/ to site/.

    bluesru-arc/content/ is the staging area populated by blues-dev/populate/populate.py.
    Files in content/ are already encoding-converted (UTF-8).
    Here we apply: SSI resolution, analytics stripping, charset normalization.
    """
    print("Processing static content from bluesru-arc/content/...")

    if not CONTENT.exists() or not any(CONTENT.iterdir()):
        print("  WARNING: bluesru-arc/content/ is empty. Run populate.py first.")
        print("  Falling back to original source directories...")
        _generate_content_from_sources()
        return

    # Sections that live in content/ subdirectories (populated from external source dirs)
    # These come from: beefheart/, ethnotrip/, zappazuhoi/, bluesnews/, atb/
    external_sections = [
        'beefheart', 'ethnotrip', 'zappazuhoi', 'bluesnews', 'atb',
    ]
    # Build set of gallery dir prefixes — skip all HTMs inside gallery dirs
    gallery_skip = _gallery_dir_prefixes()
    # Map custom gallery path prefixes → media base URL for img src rewriting
    custom_gallery_media = _build_custom_gallery_media_map()

    for name in external_sections:
        src = CONTENT / name
        if not src.exists():
            print(f"  {name}/: not in content/, skipping")
            continue
        dst = SITE / name
        # SSI resolution uses BLUES_RU as the include root for bluesnews/atb
        src_root = BLUES_RU if name in ('bluesnews', 'atb') else src
        skip = gallery_skip if name == 'bluesnews' else None
        media_map = custom_gallery_media if name == 'bluesnews' else None
        count = _copy_section(src, dst, src_root, skip_paths=skip, media_gallery_map=media_map)
        # If no index.html was generated but default.htm.1 exists, use it as index
        if not (dst / 'index.html').exists():
            for candidate in ['default.htm.1', 'default.html.1']:
                fallback = src / candidate
                if fallback.exists():
                    content = read_file(fallback)
                    if content:
                        content = process_html(content, src, src_root)
                        (dst / 'index.html').write_text(content, encoding='utf-8')
                        count += 1
                        print(f"    → {candidate} used as index.html")
                    break
        print(f"  {name}/: {count} files")

    # blues-calendar images (not in content/, copied directly from source)
    dst_cal = SITE / 'calendar'
    dst_cal.mkdir(parents=True, exist_ok=True)
    cal_count = 0
    for img in CAL_IMGS.rglob('*'):
        if img.is_file() and '.git' not in img.parts:
            dst = dst_cal / img.relative_to(CAL_IMGS)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dst)
            cal_count += 1
    print(f"  blues-calendar/: {cal_count} images")

    # blues-ru static sections live at the root of content/
    # (ad/ was excluded by populate.py)
    static_sections = [
        'rblues', 'style', 'bsfest', 'bbkingfest', 'efes', 'nbf',
        'svalbard', 'nepal', 'august', 'handy', 'mojobook', 'book',
        'reading', 'vocabulary.htm', 'about.htm', 'label',
        'ww', 'club', 'css', 'images', 'js', 'newsimg', 'stuff',
        'fest', 'article', 'harp', 'lessons', 'andrey', 'fedor', 'arc',
    ]
    sec_total = 0
    for section in static_sections:
        src = CONTENT / section
        if not src.exists():
            continue
        dst = SITE / section
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in ('.htm', '.html'):
                content = read_file(src)
                if content:
                    content = process_html(content, src.parent, CONTENT)
                    dst.write_text(content, encoding='utf-8')
                    sec_total += 1
            else:
                shutil.copy2(src, dst)
                sec_total += 1
        else:
            c = _copy_section(src, dst, CONTENT)
            sec_total += c
    print(f"  blues-ru sections/: {sec_total} files")

    # bluesmen/ in content/ — used by generate_bluesmen() via SRC_BLUESMEN override
    # (generate_bluesmen handles that separately; nothing to do here)

    # Copy static assets from bluesru-arc/static/
    _copy_dir(STATIC / 'js', SITE / 'static' / 'js')
    _copy_dir(STATIC / 'css', SITE / 'static' / 'css')
    _copy_dir(STATIC / 'forum', SITE / 'forum')
    if (STATIC / 'covers').exists():
        _copy_dir(STATIC / 'covers', SITE / 'static' / 'covers')
    print("  static/: JS + CSS + forum assets + covers copied")

    # Copy root files
    for fname in ['_redirects', '_headers', '404.html']:
        src = ARC / fname
        if src.exists():
            shutil.copy2(src, SITE / fname)
    print("  Root files: _redirects, _headers, 404.html")


def _generate_content_from_sources():
    """
    Fallback: read from original source dirs if content/ not populated.
    Used when populate.py has not been run.
    """
    sections = {
        'beefheart': (BEEFHEART, BEEFHEART),
        'ethnotrip': (ETHNOTRIP, ETHNOTRIP),
        'zappazuhoi': (ZAPPAZUHOI, ZAPPAZUHOI),
        'bluesnews': (BLUESNEWS, BLUES_RU),
        'atb': (ATB, BLUES_RU),
    }
    for name, (src, src_root) in sections.items():
        dst = SITE / name
        count = _copy_section(src, dst, src_root,
                              skip_exts=SKIP_EXTENSIONS if name == 'atb' else set())
        print(f"  {name}/: {count} files")

    dst_cal = SITE / 'calendar'
    dst_cal.mkdir(parents=True, exist_ok=True)
    cal_count = 0
    for img in CAL_IMGS.rglob('*'):
        if img.is_file() and '.git' not in img.parts:
            dst = dst_cal / img.relative_to(CAL_IMGS)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dst)
            cal_count += 1
    print(f"  blues-calendar/: {cal_count} images")

    static_sections = [
        'rblues', 'style', 'bsfest', 'bbkingfest', 'efes', 'nbf',
        'svalbard', 'nepal', 'august', 'handy', 'mojobook', 'book',
        'reading', 'vocabulary.htm', 'about.htm', 'label',
        'ww', 'club', 'css', 'images', 'js', 'newsimg', 'stuff',
        'fest', 'article', 'harp', 'lessons', 'andrey', 'fedor',
    ]
    for section in static_sections:
        src = BLUES_RU / section
        if not src.exists():
            continue
        dst = SITE / section
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in ('.htm', '.html'):
                content = read_file(src)
                if content:
                    content = process_html(content, src.parent, BLUES_RU)
                    dst.write_text(content, encoding='utf-8')
            else:
                shutil.copy2(src, dst)
        else:
            _copy_section(src, dst, BLUES_RU)

    _copy_dir(STATIC / 'js', SITE / 'static' / 'js')
    _copy_dir(STATIC / 'css', SITE / 'static' / 'css')
    _copy_dir(STATIC / 'forum', SITE / 'forum')
    for fname in ['_redirects', '_headers', '404.html']:
        src = ARC / fname
        if src.exists():
            shutil.copy2(src, SITE / fname)


def _normalize_filename(name):
    """Normalize default.htm / default.html / index.htm → index.html."""
    low = name.lower()
    if low in ('default.htm', 'default.html', 'index.htm'):
        return 'index.html'
    return name


_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'}


def _copy_section(src_dir, dst_dir, source_root, skip_exts=None, skip_paths=None,
                  media_gallery_map=None):
    """Copy a content section to site/.

    skip_paths: set of site-relative forward-slash paths to omit (per-photo gallery HTMs).
    media_gallery_map: dict of site-relative path prefix → media base URL.
      For custom gallery dirs: image files are routed to media-blues-ru/ instead of site/,
      and HTML files get their relative img src attributes rewritten to absolute media URLs.
    """
    skip_exts = (skip_exts or set()) | SKIP_EXTENSIONS
    skip_paths = skip_paths or set()
    media_gallery_map = media_gallery_map or {}
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    # Build map: src_dir/subdir/home_file → also write as index.html
    # Reads config.xml files with <... home="filename"> attribute.
    home_files: set = set()
    for cfg in src_dir.rglob('config.xml'):
        try:
            import xml.etree.ElementTree as ET
            root_el = ET.parse(cfg).getroot()
            home = root_el.get('home') or (root_el.find('.//*[@home]') or ET.Element('')).get('home', '')
            if home:
                home_files.add(cfg.parent / home)
        except Exception:
            pass

    for src_path in sorted(src_dir.rglob('*')):
        if not src_path.is_file():
            continue
        if '.git' in src_path.parts:
            continue
        ext = src_path.suffix.lower()
        if ext in skip_exts:
            continue
        # Skip HTMs inside known gallery directories (we generate index.html instead)
        if skip_paths and ext in ('.htm', '.html'):
            rel_site = str(dst_dir.relative_to(SITE) / src_path.relative_to(src_dir))
            rel_site = rel_site.replace('\\', '/')
            if any(rel_site.startswith(p) for p in skip_paths):
                continue
        rel = src_path.relative_to(src_dir)
        parts = rel.parts
        # Normalize filename in output
        out_name = _normalize_filename(src_path.name)
        if len(parts) > 1:
            dst_path = dst_dir / Path(*parts[:-1]) / out_name
        else:
            dst_path = dst_dir / out_name

        # Check if this file is inside a custom gallery dir
        rel_site_path = str(dst_dir.relative_to(SITE) / rel).replace('\\', '/')
        media_base = None
        for prefix, mbase in media_gallery_map.items():
            if rel_site_path.startswith(prefix):
                media_base = mbase
                break

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if ext in ('.htm', '.html', '.inc'):
            content = read_file(src_path)
            if content:
                content = process_html(content, src_path.parent, source_root)
                if media_base:
                    content = _rewrite_gallery_img_src(content, media_base)
                dst_path.write_text(content, encoding='utf-8')
                # If this is the config.xml "home" file, also write as index.html
                if src_path in home_files and dst_path.name.lower() != 'index.html':
                    (dst_path.parent / 'index.html').write_text(content, encoding='utf-8')
                count += 1
                continue

        if media_base and ext in _IMAGE_EXTS:
            # Route gallery images to media-blues-ru/ instead of site/
            # media_base is like "https://media.blues.ru/photo/2000/2000-10-efes"
            # We need the filesystem path, not the URL
            media_rel = media_base.removeprefix(MEDIA_BASE_URL).lstrip('/')
            media_dst = MEDIA_DIR / media_rel / rel.name
            media_dst.parent.mkdir(parents=True, exist_ok=True)
            if not media_dst.exists():
                shutil.copy2(src_path, media_dst)
            # Don't copy to site/
            count += 1
            continue

        shutil.copy2(src_path, dst_path)
        count += 1
    return count


def _copy_dir(src, dst):
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)


ATB_EPISODES_YAML  = EXTRACTED / "atb" / "episodes.yaml"


def _atb_episode_slug(ep):
    """Return a clean URL slug for an ATB episode: lowercase, dashes."""
    stem = ep['filename'].replace('.mp3', '').replace('.MP3', '')
    return re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')


def generate_atb():
    """Generate /atb/ section — 'Весь этот блюз' radio show index + episode pages."""
    print("Generating ATB (Весь этот блюз) section...")

    if not ATB_EPISODES_YAML.exists():
        print("  WARNING: extracted-data/atb/episodes.yaml not found. Run blues-dev/etl/extract_atb_mp3s.py first.")
        return

    episodes = yaml.safe_load(ATB_EPISODES_YAML.read_text(encoding='utf-8')) or []

    def _ep_summary(ep):
        """Return short summary from merged `summary` field, or first sentence of description."""
        s = ep.get('summary') or ''
        if s:
            return s
        desc = re.sub(r'<[^>]+>', '', ep.get('description') or '').strip()
        if not desc:
            return ''
        for sep in ('. ', '! ', '? '):
            idx = desc.find(sep)
            if 0 < idx < 160:
                return desc[:idx + 1]
        return desc[:160].rstrip() + ('…' if len(desc) > 160 else '')

    # Helper: get MP3 file size in MB from source atb/ dir
    ATB_SRC = (_ws_root / 'atb') if (_ws_root / 'atb').exists() else ATB

    def _mp3_size_mb(ep):
        """Return file size in MB as string like '56 MB', or ''."""
        path = ep.get('path', '')  # e.g. /atb/subdir/file.mp3
        if not path:
            return ''
        rel = path.lstrip('/')   # atb/subdir/file.mp3
        p = ATB_SRC / Path(rel).relative_to('atb')
        if not p.exists():
            return ''
        mb = p.stat().st_size / (1024 * 1024)
        return f'{mb:.0f} MB'

    # Attach slug, summary, file size to each episode
    SHOW_SUBDIRS_SET = {'', 'ATB2'}
    for ep in episodes:
        ep['slug'] = _atb_episode_slug(ep)
        ep['summary'] = _ep_summary(ep)
        ep['page_url'] = f"/atb/{ep['slug']}/"
        ep['is_show'] = ep.get('subdir', '') in SHOW_SUBDIRS_SET
        ep['size_mb'] = _mp3_size_mb(ep)

    # Group show episodes by (date, subdir) — same date/subdir = multi-part show
    from collections import OrderedDict
    SHOW_SUBDIRS_SET2 = {'', 'ATB2'}
    # Build multi-part groups for show episodes
    # Key: (date, subdir) → sorted list of show eps
    _show_groups = {}
    for ep in episodes:
        if ep['is_show']:
            key = (ep.get('date', '') or 'unknown', ep.get('subdir', ''))
            _show_groups.setdefault(key, []).append(ep)
    # Sort each group by filename for consistent part order
    for key in _show_groups:
        _show_groups[key].sort(key=lambda e: e['filename'])
    # Assign group_parts to each show episode (list of all parts in the group)
    for key, group in _show_groups.items():
        primary = group[0]
        for ep in group:
            ep['group_parts'] = group        # all parts including self
            ep['group_primary_slug'] = primary['slug']
            ep['page_url'] = f"/atb/{primary['slug']}/"  # all parts point to same page

    # Group all episodes by date for index rendering
    by_date = OrderedDict()
    for ep in episodes:
        date = ep.get('date', '') or 'unknown'
        by_date.setdefault(date, []).append(ep)

    # Sort dates newest first
    dated = [(d, eps) for d, eps in by_date.items() if d != 'unknown']
    dated.sort(key=lambda x: x[0], reverse=True)
    undated = by_date.get('unknown', [])

    # Build year groups for navigation
    year_groups = OrderedDict()
    for date_str, eps in dated:
        yr = date_str[:4]
        year_groups.setdefault(yr, []).append((date_str, eps))

    total = len(episodes)

    # ── Episode pages ──────────────────────────────────────────────────────────
    ep_page_tmpl = JINJA_ENV.from_string("""\
<!DOCTYPE html>
<html>
<head>
  <title>{{ summary or (ep.topic or ep.filename) }} — Весь этот блюз — Blues.Ru</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <link rel="shortcut icon" href="/images/bluesru.ico">
  <link rel="stylesheet" href="/static/css/site.css">
  <style>
    body { max-width: 820px; margin: 0 auto; padding: 0 1.2em; }
    .ep-meta { color: #777; font-size: 0.88em; margin-bottom: 1em; }
    .ep-body { line-height: 1.65; }
    .ep-part { margin: 1.2em 0; }
    .ep-part-label { font-size: 0.9em; color: #555; margin-bottom: 0.3em; }
    audio { display: block; width: 100%; max-width: 540px; }
    .mp3-link { font-size: 0.85em; color: #777; margin-top: 0.3em; }
  </style>
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc">

<p><a href="/"><b>Blues.Ru</b></a> &gt; <a href="/atb/">Весь этот блюз</a></p>
<hr size="1">
<h2>{{ summary or (ep.topic or ep.filename) }}</h2>
<div class="ep-meta">
  {% if ep.date %}<b>{{ ep.date }}</b> · {% endif %}Программа «Весь Этот Блюз» на Эхо Москвы 91.2 FM
</div>
{% set parts = ep.group_parts if ep.group_parts is defined else ([ep] if ep.path else []) %}
{% if parts | length > 1 %}
{% for part in parts %}
<div class="ep-part">
  <div class="ep-part-label">Часть {{ loop.index }}</div>
  <audio controls preload="none">
    <source src="{{ part.path }}" type="audio/mpeg">
    <a href="{{ part.path }}">MP3</a>
  </audio>
  <div class="mp3-link"><a href="{{ part.path }}">Скачать MP3</a>{% if part.size_mb %} ({{ part.size_mb }}){% endif %}</div>
</div>
{% endfor %}
{% elif ep.path %}
<div class="ep-part">
  <audio controls preload="none">
    <source src="{{ ep.path }}" type="audio/mpeg">
    <a href="{{ ep.path }}">MP3</a>
  </audio>
  <div class="mp3-link"><a href="{{ ep.path }}">Скачать MP3</a>{% if ep.size_mb %} ({{ ep.size_mb }}){% endif %}</div>
</div>
{% endif %}
{% if description_html %}
<div class="ep-body">{{ description_html | safe }}</div>
{% endif %}
<hr size="1">
<p><a href="/atb/">&larr; Все выпуски «Весь Этот Блюз»</a></p>
<p align="center">{{ footer }}</p>
</body>
</html>""")

    def _format_desc(desc):
        """Format episode description into HTML paragraphs."""
        if not desc:
            return ''
        desc = re.sub(r'\s*Весь Этот Блюз\s*$', '', desc.strip())
        desc = re.sub(r'\s*<a[^>]+>(?:Часть \w+\s*&gt;&gt;&gt;|>>+)</a>\s*;?\s*', ' ', desc)
        if '<' not in desc:
            parts = [p.strip() for p in re.split(r'\n\n+', desc) if p.strip()]
            if len(parts) == 1:
                parts = re.split(r'(?<=\.) {2,}(?=[А-ЯA-Z])', parts[0])
                parts = [p.strip() for p in parts if p.strip()]
            return ''.join(f'<p>{p}</p>' for p in parts) if parts else f'<p>{desc}</p>'
        else:
            desc = re.sub(r'\n{2,}', '</p><p>', desc)
            desc = re.sub(r'\n', '<br>', desc)
            return f'<p>{desc}</p>'

    ep_pages_written = 0
    # Track which slugs have been written (multi-part: only write primary once)
    written_slugs = set()
    for ep in episodes:
        if not ep.get('slug'):
            continue
        # For multi-part episodes, only write the page for the primary part
        primary_slug = ep.get('group_primary_slug', ep['slug'])
        if primary_slug in written_slugs:
            continue
        written_slugs.add(primary_slug)

        # Use primary episode for metadata/description; use group for audio players
        primary_ep = ep  # ep IS the primary (first in sorted group)
        # Collect description from all parts (use first non-empty)
        parts_list = ep.get('group_parts', [ep])
        desc = ''
        for part in parts_list:
            desc = part.get('description') or ''
            if desc:
                break
        desc_html = _format_desc(desc)

        ep_dir = SITE / 'atb' / primary_slug
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / 'index.html').write_text(
            ep_page_tmpl.render(
                ep=primary_ep,
                summary=primary_ep['summary'],
                description_html=desc_html,
                footer=FOOTER,
            ), encoding='utf-8')
        ep_pages_written += 1

    # ── ATB index page ─────────────────────────────────────────────────────────
    atb_html = """\
<!DOCTYPE html>
<html>
<head>
  <title>Blues.Ru: Весь этот блюз — архив передач</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <link rel="shortcut icon" href="/images/bluesru.ico">
  <style>
    body { max-width: 900px; margin: 0 auto; padding: 0 1em; }
    .ep-date { color: #4F62B5; font-size: 0.9em; min-width: 90px; display: inline-block; }
    .ep-summary { color: #555; font-size: 0.9em; }
    .year-section h3 { border-bottom: 1px solid #ccc; padding-bottom: 2px; }
    .ep-tracks { margin-left: 1em; font-size: 0.9em; color: #555; }
  </style>
</head>
<body bgcolor="#ffffff" text="#000000" link="#0000ff" vlink="#5511cc" alink="#00bb00">

<table cellpadding="4" cellspacing="0" border="0" align="right">
<tr><td><a href="/"><img src="/images/bluesru100x100.gif" width="100" height="100" border="0"></a></td></tr>
</table>

<p><a href="/"><b>Blues.Ru</b></a> &gt; <a href="/atb/">Весь этот блюз</a></p>
<hr size="1">
<h2>Весь этот блюз</h2>
<p>Программа «Весь этот блюз» выходила еженедельно на <b>Эхо Москвы 91.2 FM</b>.
Всего записей: {{ total }}. | <a href="/atb/archive/">Весь Этот Блюз 2000 (архив)</a></p>

<p>
{% for yr in year_groups %}
<a href="#year-{{ yr }}">{{ yr }}</a>&#32;
{% endfor %}
</p>
<hr size="1">

{% for yr, date_eps in year_groups.items() %}
<div class="year-section" id="year-{{ yr }}">
<h3>{{ yr }}</h3>
{% for date_str, eps in date_eps %}
{% set show_eps = eps | selectattr('is_show') | list %}
{% set track_eps = eps | rejectattr('is_show') | list %}
{% if show_eps %}
{# Deduplicate: show one entry per unique page_url (multi-part groups share a URL) #}
{% set seen_urls = [] %}
{% for ep in show_eps %}
{% if ep.page_url not in seen_urls %}
{% if seen_urls.append(ep.page_url) %}{% endif %}
<p>
<span class="ep-date">{{ ep.date }}</span>
<a href="{{ ep.page_url }}">{{ ep.summary or ep.topic or ep.filename }}</a>
{%- set parts = ep.group_parts if ep.group_parts is defined else [ep] %}
{%- if parts | length > 1 %} <span class="ep-parts">({{ parts | length }} части)</span>{% endif %}
</p>
{% endif %}
{% endfor %}
{% elif track_eps %}
<p>
<span class="ep-date">{{ date_str }}</span>
<b>{{ track_eps[0].subdir.split('/')[-1] | replace('_', ' ') }}</b> — {{ track_eps | length }} треков
<div class="ep-tracks">
{% for t in track_eps %}<a href="{{ t.path }}">{{ t.topic or t.filename }}</a>{% if not loop.last %} · {% endif %}{% endfor %}
</div>
</p>
{% endif %}
{% endfor %}
</div>
{% endfor %}

{% if undated %}
<h3>Без даты</h3>
{% for ep in undated %}
<p><a href="{{ ep.page_url }}">{{ ep.summary or ep.topic or ep.filename }}</a></p>
{% endfor %}
{% endif %}

<p align="center">{{ footer }}</p>
</body>
</html>"""

    tmpl = JINJA_ENV.from_string(atb_html)
    dst = SITE / 'atb' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(tmpl.render(
        total=total,
        year_groups=year_groups,
        undated=undated,
        footer=FOOTER,
    ), encoding='utf-8')
    print(f"  ATB index: {total} episodes, {len(year_groups)} years")
    print(f"  ATB episode pages: {ep_pages_written}")

    # ── latest-atb.json ────────────────────────────────────────────────────────
    # Episodes with real dates, newest first, for homepage widget
    # Include ATB2 subdir (newer show files) but exclude track-archive subdirs
    SHOW_SUBDIRS = {'', 'ATB2'}
    datable = [ep for ep in episodes if ep.get('date') and ep.get('date') != 'unknown'
               and ep.get('subdir', '') in SHOW_SUBDIRS]
    datable.sort(key=lambda e: e['date'], reverse=True)
    latest_atb = []
    for ep in datable[:8]:
        latest_atb.append({
            'date': ep['date'],
            'summary': ep['summary'],
            'url': ep['page_url'],
            'mp3': ep.get('path', ''),
        })
    atb_json_path = SITE / 'data' / 'latest-atb.json'
    atb_json_path.parent.mkdir(parents=True, exist_ok=True)
    atb_json_path.write_text(
        json.dumps({'items': latest_atb}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(f"  latest-atb.json: {len(latest_atb)} items")

    # ── Old static ATB archive ─────────────────────────────────────────────────
    atb_content = CONTENT / 'atb'
    for candidate in ['ATBr-index2000.htm', 'index.htm', 'index.html', 'index.html.1', 'default.htm.1', 'default.html.1']:
        fallback = atb_content / candidate
        if fallback.exists():
            old_content = read_file(fallback)
            if old_content:
                old_content = process_html(old_content, atb_content, BLUES_RU)
                # Fix relative image paths: archive/ is one level deeper than atb/,
                # so images that live at /atb/*.gif need src="../*.gif"
                old_content = re.sub(
                    r'(<img\b[^>]*\ssrc=")(?!https?://|/)([^"]+)(")',
                    r'\1../\2\3',
                    old_content, flags=re.IGNORECASE
                )
                # Also fix relative <a href> links to sibling ATB pages
                old_content = re.sub(
                    r'(<a\b[^>]*\shref=")(?!https?://|#|/)([^"]+\.htm[^"]*")([^>]*>)',
                    r'\1/atb/\2\3',
                    old_content, flags=re.IGNORECASE
                )
                arc_dst = SITE / 'atb' / 'archive' / 'index.html'
                arc_dst.parent.mkdir(parents=True, exist_ok=True)
                arc_dst.write_text(old_content, encoding='utf-8')
                print(f"  ATB archive: {candidate} → /atb/archive/")
            break


_RE_BLUES_RU_DOMAIN = re.compile(
    r'^https?://(?:www\.)?(?:blues\.ru|a\.blues\.ru)(/.*)$', re.IGNORECASE
)

def _rewrite_links(content):
    """
    Rewrite all internal <a href="..."> in content:
    - http(s)://blues.ru/path → /path (strip own domain)
    - Apply redirect rules (normalize paths)
    - Dead links: add class="dead-link", move href to data-dead-href, set href="#"
    """
    def _rewrite_atag(m):
        atag = m.group(0)
        href = m.group(1)
        # Strip our own domain from absolute URLs
        dm = _RE_BLUES_RU_DOMAIN.match(href)
        if dm:
            href = dm.group(1)
            atag = atag.replace(f'href="{m.group(1)}"', f'href="{href}"', 1)
        if not href.startswith('/') or href.startswith('//'):
            return atag
        new_href = _apply_redirect(href)
        path_key = new_href.split('?')[0].split('#')[0].rstrip('/') or '/'
        fix = _LINK_FIXES.get(path_key) or _LINK_FIXES.get(path_key + '/')
        if fix == 'dead':
            atag = re.sub(r'\bhref="[^"]*"', f'data-dead-href="{new_href}" href="#"', atag)
            if 'class=' not in atag:
                atag = atag.replace('<a ', '<a class="dead-link" ', 1)
            else:
                atag = re.sub(r'\bclass="([^"]*)"',
                              lambda c: f'class="{c.group(1)} dead-link"', atag, count=1)
            return atag
        return atag.replace(f'href="{href}"', f'href="{new_href}"', 1)

    return re.sub(r'<a\b[^>]*(?<![a-z-])href="(/[^"]*)"[^>]*>', _rewrite_atag, content)


def postprocess_dead_links():
    """
    Apply dead-link and redirect rewriting to all generated HTML in site/.
    process_html() handles static content files, but generated pages (calendar,
    news, forum, reviews) also contain links to old/dead content from DB data.
    This pass rewrites any remaining unprocessed links.
    """
    if not _LINK_FIXES and not _REDIRECT_RULES:
        return
    fixed = 0
    for html_file in SITE.rglob('*.html'):
        try:
            content = html_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        if 'href="/' not in content:
            continue
        new_content = _rewrite_links(content)
        if new_content != content:
            html_file.write_text(new_content, encoding='utf-8')
            fixed += 1
    print(f"  postprocess_dead_links: rewrote {fixed} files")


def generate_nbf_galleries():
    """Generate /photo/YYYY/nbf-YYYY/ photo galleries from nbf/gallery/pictures.xml."""
    # nbf/gallery is in bluesru-arc/content/nbf/gallery/
    xml_path = CONTENT / 'nbf' / 'gallery' / 'pictures.xml'
    if not xml_path.exists():
        xml_path = BLUES_RU / 'nbf' / 'gallery' / 'pictures.xml'
    if not xml_path.exists():
        print("  NBF: pictures.xml not found, skipping.")
        return

    xml_content = xml_path.read_bytes().decode('windows-1251', errors='replace')
    import html as _html

    # Parse photo entries: <p id="YY/filename.jpg">Caption</p>
    photos_raw = re.findall(r'<p id="([^"]+)"[^>]*>(.*?)</p>', xml_content, re.DOTALL)
    by_year = {}
    for pid, cap in photos_raw:
        yy = pid.split('/')[0]
        filename = pid.split('/')[-1]
        caption = _html.unescape(cap.strip())
        by_year.setdefault(yy, []).append({'filename': filename, 'caption': caption})

    year_map = {
        '98': '1998', '99': '1999', '01': '2001',
        '02': '2002', '03': '2003', '04': '2004',
    }
    year_titles = {
        '1998': 'Notodden Blues Festival 1998',
        '1999': 'Notodden Blues Festival 1999',
        '2001': 'Notodden Blues Festival 2001',
        '2002': 'Notodden Blues Festival 2002',
        '2003': 'Notodden Blues Festival 2003',
        '2004': 'Notodden Blues Festival 2004',
    }

    tmpl = JINJA_ENV.get_template('gallery.html.j2')
    src_gallery = CONTENT / 'nbf' / 'gallery'
    count = 0

    for yy, photos in by_year.items():
        year = year_map.get(yy)
        if not year:
            continue

        canonical_rel = f"photo/{year}/nbf-{year}"
        out_dir = SITE / canonical_rel
        out_dir.mkdir(parents=True, exist_ok=True)

        # Copy images from source
        src_dir = src_gallery / yy
        for photo in photos:
            fn = photo['filename']
            dst = out_dir / fn
            if not dst.exists():
                src = src_dir / fn
                if src.exists():
                    shutil.copy2(src, dst)
            # Copy thumbnail too
            stem = fn.rsplit('.', 1)[0]
            thumb_fn = f"{stem}_thumb_100.jpg"
            dst_thumb = out_dir / thumb_fn
            if not dst_thumb.exists():
                src_thumb = src_dir / thumb_fn
                if src_thumb.exists():
                    shutil.copy2(src_thumb, dst_thumb)

        # Build photo list for template
        photo_list = []
        for p in photos:
            fn = p['filename']
            stem = fn.rsplit('.', 1)[0]
            thumb_fn = f"{stem}_thumb_100.jpg"
            has_thumb = (out_dir / thumb_fn).exists()
            photo_list.append({
                'file': fn,
                'thumb': thumb_fn if has_thumb else fn,
                'caption': p['caption'],
            })

        title = year_titles.get(year, f'Notodden Blues Festival {year}')
        photos_json = json.dumps(
            [{'file': p['file'], 'caption': p['caption'], 'thumb': p.get('thumb', p['file'])}
             for p in photo_list],
            ensure_ascii=False)

        html = tmpl.render(
            path=f'nbf/gallery/{yy}',
            canonical_url=f'/{canonical_rel}/',
            title=title,
            date=year,
            description=f'Фотографии с фестиваля Notodden Blues Festival {year} (Норвегия).',
            extra_text='',
            photo_count=len(photo_list),
            photos=photo_list,
            photos_json=photos_json,
            year=year,
            source_articles=[{'url': f'/nbf/nbf{yy}.htm', 'title': f'Репортаж {year}'}
                              if (SITE / 'nbf' / f'nbf{yy}.htm').exists() else None],
            footer=FOOTER,
        )
        # Filter None entries from source_articles
        (out_dir / 'index.html').write_text(
            html.replace('<a href="None">None</a>', ''), encoding='utf-8')
        count += 1

        # Register in extra photo cards for index
        first_photo_fn = photo_list[0]['file'] if photo_list else ''
        _EXTRA_PHOTO_CARDS.append({
            'path': f'nbf/gallery/{yy}',
            'canonical_url': f'/{canonical_rel}/',
            'title': title,
            'date': year,
            'photo_count': len(photo_list),
            'thumb': first_photo_fn,
            'year': int(year),
            'year_str': year,
        })

    # Update nbf/top.inc to replace ASPX gallery links with static paths
    top_inc_src = CONTENT / 'nbf' / 'top.inc'
    if top_inc_src.exists():
        top_content = top_inc_src.read_text(encoding='utf-8')
        for yy, year in year_map.items():
            old = f'/nbf/gallery/list.aspx?y={year}'
            new = f'/photo/{year}/nbf-{year}/'
            top_content = top_content.replace(old, new)
        # Also fix the main gallery link
        top_content = top_content.replace(
            '/nbf/gallery/list.aspx',
            '/photo/2004/nbf-2004/')
        top_inc_dst = SITE / 'nbf' / 'top.inc'
        top_inc_dst.parent.mkdir(parents=True, exist_ok=True)
        top_inc_dst.write_text(top_content, encoding='utf-8')

    print(f"  NBF galleries: {count} years → site/photo/YYYY/nbf-YYYY/")


# ── Main ───────────────────────────────────────────────────────────────────────
SECTIONS = {
    'content':     generate_content,
    'forum':       generate_forum,
    'reviews':     generate_reviews,
    'news':        generate_news,
    'updates':     generate_updates,
    'bluesmen':    generate_bluesmen,
    'atb':         generate_atb,
    'galleries':   generate_galleries,
    'nbf':         generate_nbf_galleries,
    'photo':       generate_photo_index,
    'postprocess': postprocess_dead_links,
}


def main():
    args = sys.argv[1:]
    if '--section' in args:
        idx = args.index('--section')
        section = args[idx + 1]
        if section not in SECTIONS:
            print(f"Unknown section: {section}. Available: {list(SECTIONS)}")
            sys.exit(1)
        SECTIONS[section]()
    else:
        for name, fn in SECTIONS.items():
            fn()
        postprocess_dead_links()
    print(f"\nOutput: {SITE}")


if __name__ == '__main__':
    main()
