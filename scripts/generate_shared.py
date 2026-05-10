#!/usr/bin/env python3
"""
Shared constants, helpers, and data loaders for all bluesru-arc generators.

Imported by generate_forum.py, generate_reviews.py, generate_news.py, etc.
Do not run directly.
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
ARC        = Path(__file__).resolve().parent.parent
# On Cloudflare Pages (CF_PAGES=1), the output dir must be inside the repo so
# wrangler can find pages_build_output_dir="bluesru-site". Locally it sits beside.
_site_default = str(ARC / 'bluesru-site') if os.environ.get('CF_PAGES') else str(ARC.parent / 'bluesru-site')
SITE       = Path(os.environ.get('BLUESRU_SITE', _site_default))
TEMPLATES  = ARC / "templates"
INCLUDES   = ARC / "includes"
COVERS     = ARC / "covers"
CONTENT    = ARC / "content"
BLUESNEWS  = CONTENT / "bluesnews"
ATB        = CONTENT / "atb"
BEEFHEART  = CONTENT / "beefheart"
ETHNOTRIP  = CONTENT / "ethnotrip"
ZAPPAZUHOI = CONTENT / "zappazuhoi"
CAL_IMGS   = ARC / "calendar" / "images"

MEDIA_BASE_URL = ""

DATA            = ARC / "data"
ARTISTS_YAML    = DATA / "artists.yaml"
ALBUMS_DIR      = DATA / "albums"
REVIEWS_DIR     = DATA / "albums"
EVENTS_DIR      = DATA / "calendar.yaml"
ANNOUNCE_DIR    = DATA / "updates"
NEWS_DIR        = DATA / "news"
TOPICS_DIR      = DATA / "forum" / "topics"
RESOURCES_YAML  = DATA / "artists.yaml"
STREAMING_ARTISTS = DATA / "artists.yaml"
STREAMING_ALBUMS  = DATA / "albums"
GALLERIES_YAML    = DATA / "galleries" / "index.yaml"
GALLERIES_DIR     = DATA / "galleries"
CALENDAR_YAML     = DATA / "calendar.yaml"
ATB_EPISODES_YAML   = DATA / "atb" / "episodes.yaml"
ATB_TRANSCRIPTS_DIR = DATA / "atb" / "transcripts"


def _load_spam_ids():
    spam_yaml = DATA / "forum" / "spam-ids.yaml"
    if not spam_yaml.exists():
        return set()
    d = yaml.safe_load(spam_yaml.read_text(encoding='utf-8')) or {}
    return set(d.get('post_ids', []))

SPAM_IDS = _load_spam_ids()

_AUTHOR_SLUGS = None  # lazy-loaded on first forum render

def _get_author_slugs() -> dict:
    global _AUTHOR_SLUGS
    if _AUTHOR_SLUGS is None:
        p = DATA / 'forum' / 'author-slugs.json'
        if p.exists():
            _AUTHOR_SLUGS = json.loads(p.read_text(encoding='utf-8'))
        else:
            _AUTHOR_SLUGS = {}
    return _AUTHOR_SLUGS


def _poster_html(poster_escaped: str, raw_poster: str) -> str:
    """Wrap poster name in a dim link to author page if they have one, else plain span."""
    slug = _get_author_slugs().get(raw_poster, '')
    if slug:
        return (f'<a href="/forum/{slug}/" class="forum-author">'
                f'{poster_escaped}</a>')
    return poster_escaped


def _load_topics_index():
    index_yaml = DATA / "forum" / "topics-index.yaml"
    if index_yaml.exists():
        return yaml.safe_load(index_yaml.read_text(encoding='utf-8')) or []
    topics = []
    for p in TOPICS_DIR.glob('*/*.yaml'):
        d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        if d.get('topic_id'):
            topics.append({
                'topic_id': d['topic_id'],
                'slug': d.get('slug', f"topic-{d['topic_id']}"),
                'title': d.get('title', ''),
                'first_post': str(d.get('first_post', '') or ''),
                'last_post': str(d.get('last_post', '') or ''),
                'post_count': d.get('post_count', 0),
                '_path': p,
            })
    return topics


def _find_topic_yaml(topic_id):
    for p in TOPICS_DIR.glob(f'*/*-topic-{topic_id}.yaml'):
        return p
    flat = TOPICS_DIR / f'topic-{topic_id}.yaml'
    return flat if flat.exists() else None


def load_all_gallery_yamls():
    seen = set()
    galleries = []
    for p in sorted(GALLERIES_DIR.glob('*.yaml')):
        if p.stem == 'index':
            continue
        d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        if isinstance(d, dict) and d.get('slug'):
            key = (d['slug'], str(d.get('canonical_date') or ''))
            if key not in seen:
                seen.add(key)
                galleries.append(d)
    for p in sorted(GALLERIES_DIR.glob('*/*.yaml')):
        d = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        if isinstance(d, dict) and d.get('slug'):
            key = (d['slug'], str(d.get('canonical_date') or ''))
            if key not in seen:
                seen.add(key)
                galleries.append(d)
    galleries.sort(key=lambda g: (str(g.get('canonical_date') or '0000'), g.get('slug', '')))
    return galleries


_gallery_yaml_map = None

def _gallery_yaml(slug):
    global _gallery_yaml_map
    if _gallery_yaml_map is None:
        _gallery_yaml_map = {}
        for p in GALLERIES_DIR.glob('*.yaml'):
            if p.stem != 'index':
                _gallery_yaml_map[p.stem] = p
        for p in GALLERIES_DIR.glob('*/*.yaml'):
            _gallery_yaml_map[p.stem] = p
    return _gallery_yaml_map.get(slug)


# ── Jinja2 environment ─────────────────────────────────────────────────────────
JINJA_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES)),
    autoescape=False,
    undefined=jinja2.Undefined,
)

# ── Footer, GA, CSS ────────────────────────────────────────────────────────────
FOOTER = (INCLUDES / "footer.inc").read_text(encoding='utf-8').strip()
DONATE = (INCLUDES / "donate.inc").read_text(encoding='utf-8').strip()
JINJA_ENV.globals['footer'] = FOOTER
JINJA_ENV.globals['donate'] = DONATE

GA_SNIPPET = '''\
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8HDC1W9R3E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-8HDC1W9R3E');
</script>'''

SITE_CSS_TAG = (
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<link rel="stylesheet" href="/css/site.css">\n'
    '<link rel="stylesheet" href="/css/responsive.css">'
)

JINJA_ENV.globals['ga_snippet'] = GA_SNIPPET
JINJA_ENV.globals['site_css_tag'] = SITE_CSS_TAG


def star_rating_html(mark, size='1.4rem'):
    """Return HTML for star rating. mark is 0-10 integer; displayed as 0-5 stars."""
    if not mark:
        return ''
    n = int(mark)
    rating = n / 2.0  # 0-10 → 0-5 stars
    full = int(rating)
    half = (n % 2) == 1
    text = f'{rating:g} из 5'

    GOLD = '#C8952C'
    HALF = '#d4ab6a'
    GRAY = '#ccc'

    parts = []
    if full:
        parts.append(f'<span style="color:{GOLD}">{"★" * full}</span>')
    if half:
        parts.append(f'<span style="color:{HALF}">★</span>')
    empty = 5 - full - (1 if half else 0)
    if empty > 0:
        parts.append(f'<span style="color:{GRAY}">{"★" * empty}</span>')

    return f'<span class="star-rating" title="{text}">{"".join(parts)}</span> '


JINJA_ENV.globals['star_rating_html'] = star_rating_html

MONTHS_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
             'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']

# ── Redirect rules ─────────────────────────────────────────────────────────────
def _load_redirect_rules():
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
        if dst.startswith('http'):
            continue
        if '*' in src:
            prefix = src.rstrip('*').rstrip('/')
            target = dst.replace(':splat', '')
            rules.append(('wildcard', prefix, target))
        elif '?' in src:
            path_part, qs = src.split('?', 1)
            rules.append(('query', path_part, qs, dst))
        else:
            rules.append(('exact', src, dst))
    return rules

_REDIRECT_RULES = _load_redirect_rules()


def _apply_redirect(href):
    if not href or not href.startswith('/') or href.startswith('//'):
        return href
    href = re.sub(r'/index\.html?$', '/', href)
    path_part = href.split('?')[0].split('#')[0]
    if path_part and '.' not in path_part.split('/')[-1]:
        if not path_part.endswith('/') and not re.match(r'^/forum/topic\d+$', path_part):
            href = path_part + '/' + (href[len(path_part):] if len(href) > len(path_part) else '')
    path = href.split('?')[0].split('#')[0]
    for rule in _REDIRECT_RULES:
        if rule[0] == 'exact' and rule[1] == path:
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
            if rule[2] in qs:
                return rule[3]
    return href


# ── Dead link fixes ────────────────────────────────────────────────────────────
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

RE_INCLUDE_VIRTUAL = re.compile(r'<\\?!--#include\s+virtual\s*=\s*"([^"]+)"\s*-->', re.IGNORECASE)
RE_INCLUDE_FILE    = re.compile(r'<\\?!--#include\s+file\s*=\s*"([^"]+)"\s*-->', re.IGNORECASE)
RE_DYNAMIC_ASPX    = re.compile(r'<\\?!--#include\s+virtual\s*=\s*"/data/dynamic\.aspx"\s*-->', re.IGNORECASE)
RE_UNRESOLVED      = re.compile(r'<!--\s*virtual include not resolved:\s*[^-]+?-->', re.IGNORECASE)

SKIP_EXTENSIONS = {
    '.mp3', '.ram', '.rm', '.swf', '.wma', '.wav',
    '.aspx', '.ascx', '.asp', '.xsl', '.cs', '.vb',
    '.sln', '.csproj', '.resx', '.config',
}


# ── Core utilities ─────────────────────────────────────────────────────────────
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
    content = re.sub(r'<%.*?%>', '', content, flags=re.DOTALL)
    content = re.sub(r'<asp:[^>]*/>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'<asp:Content\b[^>]*>(.*?)</asp:Content>', r'\1', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<asp:[^>]*>.*?</asp:[^>]*>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a\b[^>]*allmusic\.com[^>]*>.*?</a>',
        '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a\b[^>]*href="[^"]*\.(?:ra|rm|ram)"[^>]*>\s*<img[^>]*ra\.gif[^>]*/?>\s*</a>',
        '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a\b[^>]*href="[^"]*\.ram"[^>]*>[^<]*</a>',
        '', content, flags=re.IGNORECASE)
    content = re.sub(
        r'<img\b[^>]*ra\.gif[^>]*/?>',
        '', content, flags=re.IGNORECASE)
    return content


def cover_url_for_asin(asin):
    if not asin:
        return ''
    local = COVERS / f'{asin}.jpg'
    if local.exists():
        return f'/covers/{asin}.jpg'
    return f'https://images-na.ssl-images-amazon.com/images/P/{asin}.01.MZZZZZZZ.jpg'


def format_review_body(body):
    body = body.strip()
    body = re.sub(
        r'<a\b[^>]*allmusic\.com[^>]*>(.*?)</a>',
        r'\1', body, flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(
        r'<img\b[^>]*image\.allmusic\.com[^>]*/?>', '',
        body, flags=re.IGNORECASE)
    body = re.sub(
        r'https?://(?:www\.)?allmusic\.com/\S+', '', body, flags=re.IGNORECASE)
    if not body:
        return body
    if '\n\n' not in body:
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
    if vpath_lower == '/footer.inc':
        return FOOTER
    if vpath_lower == '/donate.inc':
        return DONATE
    if vpath_lower in DROP_INCLUDES:
        return ''
    if any(kw in vpath_lower for kw in DROP_INCLUDE_KEYWORDS):
        return ''
    if '/data/dynamic.aspx' in vpath_lower:
        return ''

    candidates = []
    if vpath_lower.startswith('/'):
        rel = vpath.lstrip('/')
        candidates = [INCLUDES / rel, CONTENT / rel, source_root / rel]
    else:
        candidates = [source_dir / vpath, source_root / vpath]

    for disk_path in candidates:
        if disk_path.exists() and disk_path.is_file():
            content = read_file(disk_path)
            if content is None:
                continue
            content = strip_analytics(content)
            content = RE_INCLUDE_VIRTUAL.sub(
                lambda m: resolve_include(m.group(1), disk_path.parent, source_root), content)
            content = RE_INCLUDE_FILE.sub(
                lambda m: resolve_include(m.group(1), disk_path.parent, source_root), content)
            content = RE_DYNAMIC_ASPX.sub('', content)
            return content
    return ''


# ── Link rewriting (defined before process_html for clarity) ───────────────────
_RE_BLUES_RU_DOMAIN = re.compile(
    r'^https?://(?:www\.)?(?:blues\.ru|a\.blues\.ru)(/.*)$', re.IGNORECASE
)

def _rewrite_links(content):
    def _rewrite_atag(m):
        atag = m.group(0)
        href = m.group(1)
        dm = _RE_BLUES_RU_DOMAIN.match(href)
        if dm:
            href = dm.group(1)
            atag = atag.replace(f'href="{m.group(1)}"', f'href="{href}"', 1)
        if not href.startswith('/') or href.startswith('//'):
            return atag
        _m = re.match(r'^(/(?:artist|band)/[^/]+/)([^/]+)$', href)
        if _m:
            prefix, fname = _m.group(1), _m.group(2)
            if '_' in fname or (fname != fname.lower() and '.' in fname):
                fname_norm = fname.replace('_', '-').lower()
                if fname_norm.endswith('.htm'):
                    fname_norm = fname_norm[:-4] + '.html'
                href = prefix + fname_norm
                atag = atag.replace(f'href="{m.group(1)}"', f'href="{href}"', 1)
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


def _build_resource_links(resources, artist_slug):
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
        if r.get('type_id') == 1:
            continue
        if '.aspx' in url.lower():
            continue
        url = re.sub(r'^https?://(?:www\.)?blues\.ru', '', url, flags=re.IGNORECASE)
        if url.startswith('/bluesmen/') and artist_slug:
            rest = re.sub(r'^/bluesmen/[^/]+', '', url)
            url = f'/artist/{artist_slug}{rest}'
        elif url.startswith('/artist/') and artist_slug:
            rest = re.sub(r'^/artist/[^/]+', '', url)
            url = f'/artist/{artist_slug}{rest}'
        if re.match(r'^/ATB/.*\.mp3$', url, re.IGNORECASE):
            continue
        if re.match(r'^/atb/?$', url, re.IGNORECASE):
            continue
        if artist_slug and url.rstrip('/') == f'/artist/{artist_slug}':
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        label = name or type_short
        items.append(f'<a href="{url}">{html_mod.escape(label)}</a>')
    if not items:
        return ''
    return ' | '.join(items)


def _build_album_list_html(artist_slug, artist_id, albums_by_artist):
    import html as _html
    albums = albums_by_artist.get(str(artist_id), [])
    if not albums:
        return ''
    def _year_key(a):
        try: return -int(a.get('year', 0) or 0)
        except: return 0
    albums = sorted(albums, key=_year_key)
    parts = ['<h3>Избранные компакт-диски</h3>\n<ul>\n']
    for a in albums:
        asin = a.get('asin', '')
        album_slug = a.get('slug', '')
        url_seg = _strip_artist_prefix(artist_slug, album_slug) if album_slug else ''
        if url_seg:
            href = f'/artist/{artist_slug}/{url_seg}/'
        elif a.get('review_slug'):
            href = f'/review/{a["review_slug"]}/'
        else:
            href = '#'
        title = _html.escape(a.get('title', '') or a.get('artist', '') or '')
        year = a.get('year', '')
        label = a.get('label', '')
        year_str = f', {_html.escape(str(year))}' if year else ''
        label_str = f', <i>{_html.escape(label)}</i>' if label else ''
        cover = ''
        if asin:
            cover_url = cover_url_for_asin(asin)
            cover = f'<img src="{cover_url}" alt="" border="0" style="vertical-align:middle;margin-right:4px;" width="40" height="40">'
        parts.append(f'<li>{cover}<b><a href="{href}">{title}</a></b>{year_str}{label_str}</li>\n')
    parts.append('</ul>\n')
    return ''.join(parts)


def process_html(content, source_dir, source_root, artist_slug=None,
                 artist_name=None, artist_legacy_dir=None, artist_resources=None,
                 artist_albums_html=None, artist_atb_html=None,
                 artist_resource_links_html=None, artist_calendar_html=None):
    content = strip_analytics(content)
    content = re.sub(r'charset\s*=\s*["\']?windows-1251["\']?', 'charset=utf-8',
                     content, flags=re.IGNORECASE)
    content = re.sub(r'href="http://www\.blues\.ru/default\.htm"', 'href="/"',
                     content, flags=re.IGNORECASE)
    content = re.sub(r'href="default\.html?"', 'href="./"',
                     content, flags=re.IGNORECASE)

    if artist_slug:
        nav_block = '<hr size="1">\n'
        if artist_name and artist_legacy_dir:
            escaped_name = html_mod.escape(artist_name)
            nav_block += (
                f'<b><a href="/artist/">Музыканты</a> : '
                f'<a href="/artist/{artist_legacy_dir}/">{escaped_name}</a></b>\n'
            )
        # Use pre-built resource links if provided, otherwise fall back to legacy builder
        if artist_resource_links_html is not None:
            res_links = artist_resource_links_html
        else:
            res_links = _build_resource_links(artist_resources, artist_legacy_dir)
            stream_html = streaming_links_html(artist_slug, kind='artist')
            if stream_html:
                res_links = (res_links + ' | ' if res_links else '') + stream_html
        if res_links:
            nav_block += f'<p>{res_links}</p>\n'
        if artist_atb_html:
            nav_block += f'<p>{artist_atb_html}</p>\n'
        if artist_calendar_html:
            nav_block += f'<p>{artist_calendar_html}</p>\n'
        album_block = f'\n{nav_block}'
        if artist_albums_html:
            album_block += artist_albums_html
        replaced = RE_DYNAMIC_ASPX.sub(album_block, content)
        if replaced == content:
            # No dynamic.aspx insertion point — insert above footer.inc if present
            footer_pat = r'(<!--\s*#include\s+virtual\s*=\s*"/footer\.inc"\s*-->)'
            replaced2 = re.sub(footer_pat, album_block + '\n\\1', content, count=1, flags=re.IGNORECASE)
            if replaced2 != content:
                content = replaced2
            else:
                content = re.sub(r'(</body>)', album_block + '\n\\1', content, count=1, flags=re.IGNORECASE)
        else:
            content = replaced
    else:
        content = RE_DYNAMIC_ASPX.sub('', content)

    # Ensure footer.inc is present in artist main pages
    if artist_slug and not re.search(r'<!--\s*#include\s+virtual\s*=\s*"/footer\.inc"\s*-->', content, re.IGNORECASE):
        footer_include = '<!--#include virtual="/footer.inc"-->'
        content = re.sub(r'(</body>)', footer_include + '\n\\1', content, count=1, flags=re.IGNORECASE)

    content = RE_INCLUDE_VIRTUAL.sub(lambda m: resolve_include(m.group(1), source_dir, source_root), content)
    content = RE_INCLUDE_FILE.sub(lambda m: resolve_include(m.group(1), source_dir, source_root), content)
    content = RE_UNRESOLVED.sub('', content)
    content = _rewrite_links(content)

    if '</head>' in content.lower():
        inject = SITE_CSS_TAG + '\n' + GA_SNIPPET + '\n'
        content = re.sub(r'(</head>)', inject + '\\1', content, count=1, flags=re.IGNORECASE)
    return content


# ── Streaming data ─────────────────────────────────────────────────────────────
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

_STREAMING_ARTISTS = None
_STREAMING_ALBUMS = None


def get_streaming_artists():
    global _STREAMING_ARTISTS
    if _STREAMING_ARTISTS is None:
        result = {}
        if ARTISTS_YAML.exists():
            artists = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8')) or []
            for a in artists:
                slug = a.get('slug', '')
                ids = {}
                for key in ('spotify_id', 'apple_music_id', 'deezer_id', 'ytmusic_id'):
                    if a.get(key):
                        ids[key] = a[key]
                if ids:
                    result[slug] = ids
        _STREAMING_ARTISTS = result
    return _STREAMING_ARTISTS


def get_streaming_albums():
    global _STREAMING_ALBUMS
    if _STREAMING_ALBUMS is None:
        result = {}
        for p in ALBUMS_DIR.glob('*/*.yaml'):
            a = yaml.safe_load(p.read_text(encoding='utf-8'))
            if not a:
                continue
            slug = a.get('slug', p.stem)
            ids = {}
            for key in ('spotify_id', 'apple_music_id', 'deezer_id', 'ytmusic_id',
                        'youtube_video_id', 'youtube_playlist_id'):
                if a.get(key):
                    ids[key] = a[key]
            if ids:
                result[slug] = ids
        _STREAMING_ALBUMS = result
    return _STREAMING_ALBUMS


def streaming_links_html(slug, kind='artist'):
    data = get_streaming_artists() if kind == 'artist' else get_streaming_albums()
    info = data.get(slug, {})
    if not info:
        return ''
    templates = ARTIST_URL_TEMPLATES if kind == 'artist' else ALBUM_URL_TEMPLATES
    parts = []
    for platform, tmpl in templates.items():
        key = f'{platform}_id'
        aid = info.get(key)
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
    for p in ALBUMS_DIR.glob('*/*.yaml'):
        a = yaml.safe_load(p.read_text(encoding='utf-8'))
        if a and a.get('id'):
            albums[str(a['id'])] = a
    return albums


RE_FM = re.compile(r'^---\s*\n(.*?)\n---\s*\n(.*)', re.DOTALL)


def load_reviews():
    reviews = []
    review_by_album = {}
    for p in sorted(ALBUMS_DIR.glob('*/*.yaml')):
        album = yaml.safe_load(p.read_text(encoding='utf-8'))
        if not album:
            continue
        album_id = str(album.get('id', ''))
        for rv in album.get('reviews', []):
            meta = {
                'id': rv.get('id'),
                'album_id': album.get('id'),
                'album': album.get('title', ''),
                'artist': album.get('artist', ''),
                'artist_id': album.get('artist_id'),
                'author': rv.get('author', ''),
                'mark': rv.get('mark'),
                'date': rv.get('date'),
                'slug': f"review-{rv.get('id', '')}",
            }
            body = rv.get('text', '')
            reviews.append((meta, body))
            if album_id and album_id not in review_by_album:
                review_by_album[album_id] = meta['slug']
    return reviews, review_by_album


def load_resources():
    if not ARTISTS_YAML.exists():
        return {}
    data = yaml.safe_load(ARTISTS_YAML.read_text(encoding='utf-8'))
    if not data:
        return {}
    result = {}
    for artist in data:
        aid = str(artist.get('id', ''))
        res = artist.get('resources', [])
        if aid and res:
            type_map = {'page': 1, 'article': 2, 'discography': 3, 'photos': 4,
                        'tabs': 5, 'lyrics': 6, 'video': 7, 'audio': 8, 'links': 9, 'interview': 10}
            type_short_map = {'page': 'Страница', 'article': 'Статья', 'discography': 'Диски',
                              'photos': 'Фото', 'tabs': 'Ноты', 'lyrics': 'Тексты',
                              'video': 'Видео', 'audio': 'Аудио', 'interview': 'Интервью',
                              'link': 'Страница', 'links': 'Ссылки', 'press': 'Пресса'}
            compat = []
            for r in res:
                rtype = r.get('type', 'link')
                compat.append({
                    'type_id': type_map.get(rtype, 0),
                    'type_short': type_short_map.get(rtype, rtype),
                    'url': r.get('url', ''),
                })
            result[aid] = compat
    return result


# ── Forum rendering ────────────────────────────────────────────────────────────
_FORUM_ALLOWED_TAGS = {'b', 'i', 'u', 'strong', 'em', 'br', 's', 'strike'}
_RE_TAG = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)
_RE_HREF = re.compile(r'\bhref\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_RE_VIDEO_SRC = re.compile(
    r'\bsrc\s*=\s*["\']([^"\']*(?:youtube\.com|youtu\.be|vimeo\.com)[^"\']*)["\']',
    re.IGNORECASE
)
_RE_NUMERIC_REF = re.compile(r'&#\d+;')
_RE_BARE_URL = re.compile(r'(?<!["\'>])(https?://[^\s<>"\']+)', re.IGNORECASE)


def _autolink_bare_urls(html_text):
    def replace_url(m):
        url = m.group(1).rstrip('.,;:!?)\'\"')
        trailing = m.group(1)[len(url):]
        return f'<a href="{url}" rel="nofollow">{url}</a>{trailing}'
    return _RE_BARE_URL.sub(replace_url, html_text)


def _escape_preserving_refs(text):
    if not text:
        return text
    refs = _RE_NUMERIC_REF.findall(text)
    placeholder_map = {}
    for i, ref in enumerate(refs):
        key = f'\x00REF{i}\x00'
        placeholder_map[key] = ref
        text = text.replace(ref, key, 1)
    text = html_mod.escape(text)
    for key, ref in placeholder_map.items():
        text = text.replace(html_mod.escape(key), ref)
    return text


def sanitize_forum_html(text):
    result = []
    pos = 0
    for m in _RE_TAG.finditer(text):
        raw_before = text[pos:m.start()]
        result.append(_escape_preserving_refs(raw_before))
        pos = m.end()

        closing = m.group(1)
        tag = m.group(2).lower()
        attrs_raw = m.group(3)

        if tag in _FORUM_ALLOWED_TAGS:
            result.append(f'<{closing}{tag}>')
        elif tag == 'a' and not closing:
            href_m = _RE_HREF.search(attrs_raw)
            if href_m:
                href = href_m.group(1)
                if not re.match(r'^\s*javascript:', href, re.IGNORECASE):
                    result.append(f'<a href="{html_mod.escape(href)}" rel="nofollow noopener">')
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

    result.append(_escape_preserving_refs(text[pos:]))
    return ''.join(result)


def format_forum_date(date_str):
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
    # Spam posts (and their subtrees) are fully suppressed — no output at all
    if pid in SPAM_IDS:
        return ''
    raw_poster = post.get('poster', '') or ''
    poster_escaped = html_mod.escape(raw_poster)
    poster = _poster_html(poster_escaped, raw_poster)
    date_str = format_forum_date(post.get('date', ''))
    subject = html_mod.escape(post.get('subject', '') or '')
    text = post.get('text', '') or ''
    deleted = post.get('deleted', False)
    replies = post.get('replies', [])

    if deleted:
        text_html = ''
    else:
        sanitized = sanitize_forum_html(text)
        sanitized = _autolink_bare_urls(sanitized)
        sanitized = re.sub(r'\n', '</p><p>', sanitized)
        text_html = f'<p>{sanitized}</p>' if text else ''

    if full and depth == 0:
        html = f'<div class="message"><a name="post{pid}"></a>'
        if text_html:
            html += f'<div class="text">{text_html}</div>'
        for reply in replies:
            html += render_post_html(reply, topic_slug, full=True, depth=1)
        html += '</div>'
    elif full:
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
    slug = f'topic{topic_id}' if topic_id else topic_meta.get('slug', f'topic-{topic_id}')
    posts = topic_data.get('posts', []) if topic_data else []

    if not posts:
        return ''

    if full:
        first = posts[0]
        raw_first_poster = first.get('poster', '') or ''
        first_poster = _poster_html(html_mod.escape(raw_first_poster), raw_first_poster)
        first_date = format_forum_date(first.get('date', ''))
        subject = html_mod.escape(posts[0].get('subject', '') or topic_meta.get('title', '') or '')

        page_url = '/forum/' if forum_page <= 1 else f'/forum/page{forum_page}.html'
        forum_back = f'{page_url}#topic{topic_id}'
        html = f'<div class="topic-header">'
        html += f'<a href="{forum_back}">Blues.Ru &rsaquo; Форум</a> &rsaquo;\n'
        html += f'  <span class="subject">{subject}</span>\n'
        html += f'    &mdash; <span class="name">{first_poster}</span>\n'
        html += f'      <span class="date">({first_date})</span>'
        html += f'</div>'
        html += f'<div class="topic"><a name="topic{topic_id}"></a>'
        for post in posts:
            html += render_post_html(post, slug, full=True)
        html += '</div>'
    else:
        html = f'<div class="topic"><a name="topic{topic_id}"></a>'
        for post in posts:
            html += render_post_html(post, slug, full=False)
        html += '</div>'

    return html


def _topic_is_all_deleted(topic_data):
    def has_visible(posts):
        for p in posts:
            pid = p.get('id')
            if pid in SPAM_IDS:
                continue  # spam post + subtree suppressed entirely
            if not p.get('deleted', False):
                return True
            if has_visible(p.get('replies', [])):
                return True
        return False
    if topic_data is None:
        return True
    return not has_visible(topic_data.get('posts', []))


def _forum_visible_topics():
    topics_index = _load_topics_index()
    topics_sorted = sorted(
        topics_index,
        key=lambda t: int(t.get('topic_id', 0)),
        reverse=True,
    )
    topics_visible = []
    for tm in topics_sorted:
        tf = tm.get('_path') or _find_topic_yaml(tm['topic_id'])
        if not tf or not tf.exists():
            continue
        td = yaml.safe_load(tf.read_text())
        if not _topic_is_all_deleted(td):
            topics_visible.append(tm)
    PAGE_SIZE = 50
    topic_to_page = {
        tm['topic_id']: (i // PAGE_SIZE) + 1
        for i, tm in enumerate(topics_visible)
    }
    return topics_visible, topic_to_page


# ── Common section helpers ─────────────────────────────────────────────────────
def _strip_artist_prefix(a_slug, album_slug):
    if a_slug and a_slug != 'various-musicians' and album_slug.startswith(a_slug + '-'):
        return album_slug[len(a_slug) + 1:]
    return album_slug


def format_news_body_simple(body):
    body = body.strip()
    if not body:
        return body
    if re.search(r'<p[\s>]', body, re.IGNORECASE):
        body = re.sub(r'</p>\s*\n+\s*<p>', '</p><p>', body, flags=re.IGNORECASE)
        return body
    if '\n\n' in body:
        parts = re.split(r'\n{2,}', body)
        result = []
        for part in parts:
            part = part.strip()
            if part:
                result.append('<p>' + part + '</p>')
        return '\n'.join(result)
    return '<p>' + body + '</p>'


def _load_artist_reviews():
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


def _generate_stub_artist_page(artist, reviews_list, albums, artist_atb_html=None, artist_resource_links_html=None, artist_calendar_html=None):
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
    first_meta = reviews_list[0][0] if reviews_list else {}
    album_id = str(first_meta.get('album_id', ''))
    album = albums.get(album_id, {})

    # If resource_links_html already contains streaming, don't duplicate in "Альбом на:"
    artist_streaming = '' if artist_resource_links_html else streaming_links_html(slug, kind='artist')
    out = tmpl.render(
        album={'title': '', 'artist': name, 'year': '', 'label': '', 'asin': '', 'amg_id': amg_id},
        cover_url='',
        artist_name=name,
        artist_legacy_path='',
        reviews=reviews_data,
        streaming_links='',
        artist_streaming_links=artist_streaming,
        artist_atb_links=artist_atb_html or '',
        artist_resource_links=artist_resource_links_html or '',
        artist_calendar_links=artist_calendar_html or '',
        footer=FOOTER,
    )

    dst = SITE / 'artist' / slug / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding='utf-8')
    return dst


def _build_atb_by_slug():
    if not ATB_EPISODES_YAML.exists():
        return {}
    episodes = yaml.safe_load(ATB_EPISODES_YAML.read_text(encoding='utf-8')) or []
    index = {}
    for ep in episodes:
        for tag in (ep.get('artists_tags') or []):
            slug = tag.get('slug', '') if isinstance(tag, dict) else tag
            if not slug:
                continue
            index.setdefault(slug, []).append({
                'summary': ep.get('summary') or ep.get('topic') or ep['slug'],
                'page_url': f"/atb/{ep['slug']}/",
                'date': ep.get('date', ''),
            })
    return index


def _atb_links_html(atb_episodes):
    if not atb_episodes:
        return ''
    lines = []
    for ep in sorted(atb_episodes, key=lambda e: e.get('date', ''), reverse=True):
        label = html_mod.escape(ep['summary'])
        url = ep['page_url']
        date = ep.get('date', '')
        date_str = f'<small style="color:#777">{html_mod.escape(date)}</small> ' if date else ''
        lines.append(f'{date_str}<a href="{url}">{label}</a>')
    return '<b>Весь этот блюз:</b><br>' + '<br>'.join(lines)


def build_calendar_by_slug():
    """Return {artist_slug: [event_dict, ...]} sorted by date, from calendar.yaml."""
    if not CALENDAR_YAML.exists():
        return {}
    events = yaml.safe_load(CALENDAR_YAML.read_text(encoding='utf-8')) or []
    index = {}
    for ev in events:
        slug = ev.get('artist_slug', '') or ''
        if not slug:
            continue
        date_str = str(ev.get('date', '') or '')
        index.setdefault(slug, []).append({
            'date': date_str,
            'year': ev.get('year', ''),
            'month_day': ev.get('month_day', ''),
            'event_type': ev.get('event_type', ''),
            'title': ev.get('title', ''),
            'text': ev.get('text', ''),
            'picture': ev.get('picture', '') or '',
            'artist_slug': slug,
        })
    for slug in index:
        index[slug].sort(key=lambda e: e.get('date', ''))
    return index


def _years_ago_ru(years: int) -> str:
    """Return 'N лет/год/года назад'."""
    if years <= 0:
        return ''
    n = abs(years) % 100
    n1 = n % 10
    if 11 <= n <= 19:
        word = 'лет'
    elif n1 == 1:
        word = 'год'
    elif 2 <= n1 <= 4:
        word = 'года'
    else:
        word = 'лет'
    return f'{years}\u00a0{word} назад'


def link_artist_in_text(text: str, title: str, slug: str) -> str:
    """
    Replace first occurrence of title (case-insensitive) in text (outside existing tags)
    with a link to /artist/{slug}/#calendar.
    If not found in text, prepend a linked mention.
    """
    if not text or not title or not slug:
        return text
    link = f'<a href="/artist/{slug}/#calendar">'
    # Build case-insensitive pattern, avoid matching inside existing <a ...> </a>
    pattern = re.compile(re.escape(title), re.IGNORECASE)
    # Simple approach: find first match not inside an existing link
    # Split on existing <a ...>...</a> to avoid modifying them
    parts = re.split(r'(<a\s[^>]*>.*?</a>)', text, flags=re.DOTALL)
    replaced = False
    result = []
    for part in parts:
        if replaced or part.startswith('<a '):
            result.append(part)
        else:
            m = pattern.search(part)
            if m:
                found = m.group(0)
                repl = f'{link}{found}</a>'
                result.append(part[:m.start()] + repl + part[m.end():])
                replaced = True
            else:
                result.append(part)
    if replaced:
        return ''.join(result)
    # Not found: prepend linked title
    return f'{link}{html_mod.escape(title)}</a>. {text}'


def calendar_events_html(events: list, current_year: int = 2026) -> str:
    """Render calendar events as an HTML table block for artist pages."""
    if not events:
        return ''
    EVENT_TYPE_RU = {
        'born': 'Родился',
        'died': 'Умер',
        'founded': 'Основан',
        'other': '',
    }
    rows = []
    rows.append('<a name="calendar" id="calendar"></a>')
    rows.append('<b>Календарь:</b>')
    rows.append('<table style="border-collapse:collapse;width:100%">')
    for ev in events:
        date = ev.get('date', '')
        year = date[:4] if date and len(date) >= 4 else str(ev.get('year', ''))
        md = ev.get('month_day', '')
        if md and len(md) == 5:
            day_month = f'{md[3:5]}.{md[:2]}'
        else:
            day_month = ''
        etype = ev.get('event_type', '')
        etype_ru = EVENT_TYPE_RU.get(etype, '')
        text = ev.get('text', '') or ''
        picture = ev.get('picture', '') or ''
        title = ev.get('title', '')
        slug = ev.get('artist_slug', '')
        years_ago = (current_year - int(year)) if year and year.isdigit() else 0

        cal_url = f'/calendar/{year}/' if year else '/calendar/'
        year_cell = (f'<td style="font-weight:bold;font-size:1.1em;white-space:nowrap;'
                     f'vertical-align:top;padding:2px 6px 2px 0;width:1%">'
                     f'<a href="{cal_url}" style="color:#333">{html_mod.escape(year)}</a></td>')

        meta_parts = []
        if day_month:
            meta_parts.append(html_mod.escape(day_month))
        if years_ago > 0:
            meta_parts.append(f'<span style="color:#888;font-size:0.85em">({_years_ago_ru(years_ago)})</span>')
        if etype_ru:
            meta_parts.append(f'<span style="color:#555;font-size:0.85em">{html_mod.escape(etype_ru)}</span>')
        meta_cell = (f'<td style="white-space:nowrap;vertical-align:top;padding:2px 8px 2px 0;'
                     f'color:#555;font-size:0.88em;width:1%">{" ".join(meta_parts)}</td>')

        # Text cell: link artist name in text, include image
        if text and title and slug:
            text = link_artist_in_text(text, title, slug)
        img_html = ''
        if picture:
            img_html = (f'<img src="/calendar/images/{html_mod.escape(picture)}" border="0" '
                        f'align="right" vspace="2" hspace="6" '
                        f'style="max-width:140px;max-height:100px;">')
        text_cell = f'<td style="vertical-align:top;padding:2px 0">{img_html}{text}</td>'

        rows.append(f'<tr>{year_cell}{meta_cell}{text_cell}</tr>')
    rows.append('</table>')
    return '\n'.join(rows)


def _build_galleries_by_slug():
    """Return {artist_slug: [gallery_dict, ...]} for galleries with artists_tags."""
    if not GALLERIES_YAML.exists():
        return {}
    galleries = yaml.safe_load(GALLERIES_YAML.read_text(encoding='utf-8')) or []
    index = {}
    for g in galleries:
        tags = g.get('artists_tags') or []
        if not tags:
            continue
        slug = g.get('slug', '')
        gpath, year = _gallery_canonical_url(g, slug)
        if not year:
            continue
        url = f'/{gpath}/'
        entry = {
            'slug': slug,
            'title': g.get('title', ''),
            'url': url,
            'date': str(g.get('canonical_date', '') or ''),
        }
        for artist_slug in tags:
            index.setdefault(artist_slug, []).append(entry)
    return index


# Sub-page patterns: (filename_pattern, label, resource_type)
# Ordered by priority; first match wins for each type.
_SUBPAGE_PATTERNS = [
    # tabs
    ('tabs.html', 'Ноты', 'tabs'),
    # lyrics
    ('lyrics.html', 'Тексты', 'lyrics'),
    # photos
    ('photos.html', 'Фото', 'photos'),
    # press
    ('press.html', 'Пресса', 'press'),
]

# Glob patterns for interview / article multi-name files
_INTERVIEW_GLOBS = ['*interv*.html', 'interview.html', '*_int.html', '*_interview.html']
_ARTICLE_GLOBS   = ['article.html', '*article*.html', '*_article.html']
_ARTICLE_EXCLUDE = {'allman-brothers'}  # article.html contains something else

_SERIES_RE = re.compile(r'^(.+?)-0*(\d+)\.html?$', re.IGNORECASE)


def _scan_artist_subpages(artist_dir, artist_slug):
    """
    Scan content/artist/{slug}/ and return list of resource dicts:
        {'type': ..., 'url': ..., 'label': ...}
    Only includes files that actually exist.
    """
    if not artist_dir or not artist_dir.exists():
        return []

    resources = []
    found_types = set()
    base = f'/artist/{artist_slug}'

    # 1. Simple named files
    for filename, label, rtype in _SUBPAGE_PATTERNS:
        if rtype in found_types:
            continue
        f = artist_dir / filename
        if f.exists():
            resources.append({'type': rtype, 'url': f'{base}/{filename}', 'label': label})
            found_types.add(rtype)
        elif rtype == 'tabs' and (artist_dir / 'tabs').is_dir():
            resources.append({'type': rtype, 'url': f'{base}/tabs/', 'label': label})
            found_types.add(rtype)

    # 2. Interview files (various naming conventions)
    if 'interview' not in found_types:
        for glob_pat in _INTERVIEW_GLOBS:
            matches = sorted(artist_dir.glob(glob_pat))
            if matches:
                fname = matches[0].name
                resources.append({'type': 'interview', 'url': f'{base}/{fname}', 'label': 'Интервью'})
                found_types.add('interview')
                break

    # 3. Article files
    if 'article' not in found_types and artist_slug not in _ARTICLE_EXCLUDE:
        for glob_pat in _ARTICLE_GLOBS:
            matches = sorted(artist_dir.glob(glob_pat))
            if matches:
                fname = matches[0].name
                resources.append({'type': 'article', 'url': f'{base}/{fname}', 'label': 'Статья'})
                found_types.add('article')
                break

    # 4. Multi-page article series (e.g. canned-heat-01.html … canned-heat-06.html)
    if 'series' not in found_types:
        series_groups = {}
        for f in artist_dir.iterdir():
            if f.suffix.lower() not in ('.html', '.htm'):
                continue
            m = _SERIES_RE.match(f.name)
            if not m:
                continue
            prefix = m.group(1)
            num = int(m.group(2))
            series_groups.setdefault(prefix, []).append((num, f.name))
        for prefix, entries in series_groups.items():
            if len(entries) < 2:
                continue
            entries.sort()
            first = entries[0][1]
            resources.append({'type': 'article', 'url': f'{base}/{first}', 'label': 'Статья'})
            found_types.add('article')
            found_types.add('series')
            break  # one series per artist is enough

    return resources


def _find_main_htm(src_dir):
    dir_name = src_dir.name
    skip_sfx = ['_lyr', '_tab', '_lyric', '_lyrics', '_tabs']
    INDEX_NAMES = ('index.htm', 'index.html')
    htm_files = [
        f for f in sorted(src_dir.iterdir())
        if f.suffix.lower() in ('.htm', '.html')
        and f.name.lower() not in ('default.htm', 'default.html')
        and not any(f.stem.lower().endswith(s) for s in skip_sfx)
    ]
    if not htm_files:
        return None
    for f in htm_files:
        if f.name.lower() in INDEX_NAMES:
            return f
    dir_lower = dir_name.lower()
    for f in htm_files:
        if f.stem.lower() == dir_lower:
            return f
    return htm_files[0]


def _normalize_filename(name):
    low = name.lower()
    if low in ('default.htm', 'default.html', 'index.htm'):
        return 'index.html'
    return name


def _process_artist_dir(artist, src_dir, src_root, artist_resources=None, artist_albums_html=None, artist_atb_html=None, artist_resource_links_html=None, artist_calendar_html=None):
    slug = artist.get('slug', '')
    legacy_dir = src_dir.name
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
                    artist_albums_html=artist_albums_html if is_main else None,
                    artist_atb_html=artist_atb_html if is_main else None,
                    artist_resource_links_html=artist_resource_links_html if is_main else None,
                    artist_calendar_html=artist_calendar_html if is_main else None,
                )
                dst_path.write_text(content, encoding='utf-8')
                if is_main_rename and src_path.name.lower() not in ('default.htm', 'default.html', 'index.htm', 'index.html'):
                    orig_dst = dst_dir / _normalize_filename(src_path.name)
                    if orig_dst != dst_path:
                        orig_dst.write_text(content, encoding='utf-8')
                        if orig_dst.suffix == '.html':
                            orig_dst.with_suffix('.htm').write_text(content, encoding='utf-8')
                if dst_path.suffix == '.html' and dst_path.name != 'index.html':
                    htm_alias = dst_path.with_suffix('.htm')
                    if htm_alias != dst_path:
                        htm_alias.write_text(content, encoding='utf-8')
                # Also write the _rewrite_links-normalized filename so it resolves
                raw_fname = src_path.name
                if '_' in raw_fname or (raw_fname != raw_fname.lower() and '.' in raw_fname):
                    norm_name = raw_fname.replace('_', '-').lower()
                    if norm_name.endswith('.htm'):
                        norm_name = norm_name[:-4] + '.html'
                    norm_path = dst_path.parent / norm_name
                    if norm_path != dst_path and norm_name != 'index.html':
                        norm_path.write_text(content, encoding='utf-8')
                continue
        shutil.copy2(src_path, dst_path)


# ── Gallery helpers ────────────────────────────────────────────────────────────
def _gallery_year(path):
    top = path.split('/')[0].lstrip('_')
    m = re.search(r'((?:19|20)\d\d)', top)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    m = re.match(r'^(\d\d)[^0-9]', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    m = re.match(r'^(\d\d)$', top)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy <= 30 else 1900 + yy
        if 1995 <= year <= 2030:
            return year
    return None


def _gallery_canonical_url(data, gpath):
    canonical_date = data.get('canonical_date') or ''
    gallery_slug = data.get('slug') or re.sub(r'[^a-z0-9]+', '-', gpath.lower()).strip('-')

    m = re.match(r'^(\d{4})', str(canonical_date))
    if m:
        year_str = m.group(1)
    else:
        year = _gallery_year(gpath)
        year_str = str(year) if year else 'misc'

    cd = str(canonical_date)
    if re.match(r'^\d{4}-\d{2}-\d{2}$', cd):
        date_prefix = cd
    elif re.match(r'^\d{4}-\d{2}$', cd):
        date_prefix = cd
    elif re.match(r'^\d{4}$', cd):
        date_prefix = cd
    else:
        date_prefix = year_str

    clean_slug = gallery_slug
    clean_slug = re.sub(r'-\d{4}-\d{2}-\d{2}$', '', clean_slug).rstrip('-')
    clean_slug = re.sub(r'-\d{4}-\d{2}$', '', clean_slug).rstrip('-')
    clean_slug = re.sub(r'-\d{4}$', '', clean_slug).rstrip('-')
    if not clean_slug:
        clean_slug = gallery_slug

    if gallery_slug.startswith(date_prefix):
        dir_name = gallery_slug
    else:
        dir_name = f"{date_prefix}-{clean_slug}"
    return f"photo/{year_str}/{dir_name}", year_str


def _write_gallery_redirects(redirects):
    redirects_file = ARC / '_redirects'
    if not redirects_file.exists():
        return
    content = redirects_file.read_text(encoding='utf-8')
    marker_start = '# BEGIN gallery-redirects'
    marker_end = '# END gallery-redirects'
    if marker_start in content:
        start = content.index(marker_start)
        end = content.index(marker_end) + len(marker_end)
        content = content[:start].rstrip() + '\n' + content[end:].lstrip('\n')
    lines = [marker_start]
    for old, new in redirects:
        old_encoded = old.replace(' ', '%20')
        lines.append(f"{old_encoded}  {new}  301")
    lines.append(marker_end)
    content = content.rstrip('\n') + '\n\n' + '\n'.join(lines) + '\n'
    redirects_file.write_text(content, encoding='utf-8')


def _gallery_dir_prefixes():
    galleries = load_all_gallery_yamls()
    prefixes = set()
    for g in galleries:
        gtype = g.get('type', '')
        if gtype == 'custom':
            continue
        gpath = g.get('path', '')
        if not gpath:
            slug = g.get('slug', '')
            per = _gallery_yaml(slug)
            if per and per.exists():
                gpath = (yaml.safe_load(per.read_text(encoding='utf-8')) or {}).get('path', '')
        if not gpath:
            continue
        prefixes.add(f"bluesnews/{gpath}/")
        if gpath.endswith('/content'):
            prefixes.add(f"bluesnews/{gpath[:-8]}/")
    return prefixes


def _build_custom_gallery_media_map():
    galleries = load_all_gallery_yamls()
    result = {}
    for g in galleries:
        gtype = g.get('type', '')
        if gtype != 'custom':
            continue
        yaml_slug = g.get('slug', '')
        if not yaml_slug:
            gpath_raw = g.get('path', '')
            yaml_slug = re.sub(r'[^a-z0-9]+', '-', gpath_raw.lower()).strip('-')
        per_yaml = _gallery_yaml(yaml_slug)
        if not per_yaml or not per_yaml.exists():
            continue
        data = yaml.safe_load(per_yaml.read_text(encoding='utf-8')) or {}
        gpath = data.get('path', '') or g.get('path', '')
        if not gpath:
            continue
        canonical_rel, _ = _gallery_canonical_url(data, gpath)
        prefix = f"bluesnews/{gpath}/"
        result[prefix] = f"{MEDIA_BASE_URL}/{canonical_rel}"
    return result


def _rewrite_gallery_img_src(html_content, media_base_url):
    img_exts = r'(?i)\.(jpg|jpeg|png|gif|bmp|webp)'

    def rewrite_attr(m):
        attr = m.group(1)
        quote = m.group(2)
        val = m.group(3)
        if val.startswith(('http://', 'https://', '/', '#', 'mailto:', 'javascript:')):
            return m.group(0)
        if re.search(img_exts, val.split('?')[0].split('#')[0]):
            clean = val.lstrip('./')
            return f'{attr}={quote}{media_base_url}/{clean}{quote}'
        return m.group(0)

    pattern = re.compile(r'(src|href)=(["\'])([^"\']+)\2', re.IGNORECASE)
    return pattern.sub(rewrite_attr, html_content)


# ── Content section helpers ────────────────────────────────────────────────────
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'}


def _normalize_filename(name):
    low = name.lower()
    if low in ('default.htm', 'default.html', 'index.htm'):
        return 'index.html'
    return name


def _copy_section(src_dir, dst_dir, source_root, skip_exts=None, skip_paths=None,
                  media_gallery_map=None):
    skip_exts = (skip_exts or set()) | SKIP_EXTENSIONS
    skip_paths = skip_paths or set()
    media_gallery_map = media_gallery_map or {}
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0

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
        if skip_paths and ext in ('.htm', '.html'):
            rel_site = str(dst_dir.relative_to(SITE) / src_path.relative_to(src_dir))
            rel_site = rel_site.replace('\\', '/')
            if any(rel_site.startswith(p) for p in skip_paths):
                continue
        rel = src_path.relative_to(src_dir)
        parts = rel.parts
        out_name = _normalize_filename(src_path.name)
        if len(parts) > 1:
            dst_path = dst_dir / Path(*parts[:-1]) / out_name
        else:
            dst_path = dst_dir / out_name

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
                if src_path in home_files and dst_path.name.lower() != 'index.html':
                    (dst_path.parent / 'index.html').write_text(content, encoding='utf-8')
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


# ── ATB helpers ────────────────────────────────────────────────────────────────
def _atb_episode_slug(ep):
    if ep.get('slug'):
        return ep['slug']
    stem = ep['filename'].replace('.mp3', '').replace('.MP3', '')
    return re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')


def _parse_transcript_md(md_text):
    if not md_text:
        return []
    ANCHOR_RE = re.compile(r'<a id="([tm])(\d+)"></a>')
    MUSIC_RE  = re.compile(r'\*\*\[MUSIC:\s*(\d+):(\d+)\s*[–\-]\s*(\d+):(\d+)\]\*\*')
    parts = ANCHOR_RE.split(md_text)
    blocks = []
    i = 1
    while i + 2 < len(parts):
        kind, raw_secs, content = parts[i], parts[i+1], parts[i+2].strip()
        try:
            secs = int(raw_secs)
        except ValueError:
            i += 3
            continue
        if kind == 't':
            content = re.sub(r'\*\*\[\d+:\d+(?::\d+)?\]\*\*\s*', '', content).strip()
            paras = [p.strip() for p in content.split('\n\n') if p.strip()]
            if paras:
                html_t = ''.join(f'<p>{p}</p>' for p in paras)
                blocks.append({'type': 'speech', 'seconds': secs, 'text': html_t})
        elif kind == 'm':
            m = MUSIC_RE.search(content)
            if m:
                end_s = int(m.group(3)) * 60 + int(m.group(4))
                blocks.append({'type': 'music', 'seconds': secs, 'end_seconds': end_s})
        i += 3
    return blocks


def _fmt_tc(s):
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _transcript_to_html(blocks, part_index):
    if not blocks:
        return ''
    out = []
    for b in blocks:
        t = b['seconds']
        tc = _fmt_tc(t)
        anchor = f'p{part_index}t{t}'
        if b['type'] == 'speech':
            out.append(
                f'<div class="atb-speech" id="{anchor}">'
                f'<button class="atb-tc" onclick="atbSeek({part_index},{t})">{tc}</button>'
                f'<div class="atb-speech-text">{b["text"]}</div>'
                f'</div>'
            )
        else:
            dur = b['end_seconds'] - t
            out.append(
                f'<div class="atb-music" id="{anchor}" onclick="atbSeek({part_index},{t})" role="button" tabindex="0">'
                f'<span class="atb-m-note">&#9835;</span>'
                f'<span class="atb-m-start">{tc}</span>'
                f'<span class="atb-m-dur">&thinsp;&middot;&thinsp;{_fmt_tc(dur)}</span>'
                f'</div>'
            )
    return '\n'.join(out)


# ── Links page helpers ─────────────────────────────────────────────────────────
def _build_links_snippet(categories, sites):
    def get_blues_cat_ids(root_id='1'):
        result = {root_id}
        changed = True
        while changed:
            changed = False
            for c in categories.values():
                if c['id'] not in result and c.get('parent_id') in result:
                    result.add(c['id'])
                    changed = True
        return result

    blues_ids = get_blues_cat_ids()
    live_statuses = {'live', 'redirected'}
    blues_sites = [
        s for s in sites
        if any(cid in blues_ids for cid in s.get('categories', []))
        and s.get('status', '') in live_statuses
    ]
    top_cats = [c for c in categories.values() if c.get('parent_id') == '1']
    by_cat = {}
    for site in blues_sites:
        for cid in site.get('categories', []):
            if cid in blues_ids:
                by_cat.setdefault(cid, []).append(site)

    html = '<b><a href="/links/">Блюзовые ссылки</a></b>\n<ul>\n'
    for cat in sorted(top_cats, key=lambda c: c.get('name', '')):
        cat_sites = by_cat.get(cat['id'], [])
        if not cat_sites:
            continue
        html += f'<li><b>{cat["name"]}</b><ul>\n'
        for site in cat_sites[:5]:
            html += f'  <li><a href="{site["url"]}">{html_mod.escape(site["name"])}</a></li>\n'
        if len(cat_sites) > 5:
            html += f'  <li><a href="/links/"><small>ещё {len(cat_sites)-5}...</small></a></li>\n'
        html += '</ul></li>\n'
    html += f'</ul>\n<p><a href="/links/">Все ссылки &gt;&gt;</a></p>\n'
    return html


def _generate_links_page(categories, sites):
    def get_blues_cat_ids(root_id='1'):
        result = {root_id}
        changed = True
        while changed:
            changed = False
            for c in categories.values():
                if c['id'] not in result and c.get('parent_id') in result:
                    result.add(c['id'])
                    changed = True
        return result

    blues_ids = get_blues_cat_ids()
    live_statuses = {'live', 'redirected', 'unknown'}
    blues_sites = [
        s for s in sites
        if any(cid in blues_ids for cid in s.get('categories', []))
        and s.get('status', 'unknown') in live_statuses
    ]
    by_cat = {}
    for site in blues_sites:
        for cid in site.get('categories', []):
            if cid in blues_ids:
                by_cat.setdefault(cid, []).append(site)

    top_cats = [c for c in categories.values() if c.get('parent_id') == '1']
    child_cats = {}
    for c in categories.values():
        if c.get('parent_id'):
            child_cats.setdefault(c['parent_id'], []).append(c)

    def render_cat(cat, depth=0):
        cid = cat['id']
        cat_sites = by_cat.get(cid, [])
        child_list = sorted(child_cats.get(cid, []), key=lambda c: c.get('name', ''))
        if not cat_sites and not child_list:
            return ''
        hn = f'h{"23456"[min(depth, 4)]}'
        s = f'<{hn}>{cat["name"]}</{hn}>\n'
        if cat_sites:
            s += '<ul>\n'
            for site in sorted(cat_sites, key=lambda x: x.get('name', '')):
                desc = f' — {html_mod.escape(site["description"])}' if site.get('description') else ''
                s += f'  <li><a href="{site["url"]}">{html_mod.escape(site["name"])}</a>{desc}</li>\n'
            s += '</ul>\n'
        for child in child_list:
            s += render_cat(child, depth + 1)
        return s

    html = ('<!DOCTYPE html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<title>Блюзовые ссылки — Blues.Ru</title>\n'
            '<link rel="shortcut icon" href="/images/bluesru.ico">\n'
            '<link rel="stylesheet" href="/css/site.css">\n'
            '<link rel="stylesheet" href="/css/responsive.css">\n'
            + GA_SNIPPET + '\n'
            '<style>a{text-decoration:none} body{max-width:900px;margin:0 auto;padding:0 1em}</style>\n'
            '</head>\n<body bgcolor="#FFFFFF" text="#000000" link="#0000FF" vlink="#5511CC">\n'
            '<a href="/"><img src="/images/bluesru-logo.svg" width="120" height="120" border="0" alt="Blues.Ru" style="float:right"></a>\n'
            '<p><a href="/"><b>Blues.Ru</b></a> &gt; Ссылки</p>\n'
            '<h1>Блюзовые ссылки</h1>\n'
            '<p>Ссылки на сайты о блюзе. Собраны в 2001–2009 годах; показаны работавшие на момент проверки.</p>\n')
    for cat in sorted(top_cats, key=lambda c: c.get('name', '')):
        html += render_cat(cat)
    dead_count = sum(
        1 for s in sites
        if any(cid in blues_ids for cid in s.get('categories', []))
        and s.get('status') in ('dead', 'changed')
    )
    html += (f'<hr size="1">\n<p align="center">{FOOTER}</p>\n</body>\n</html>')
    out = SITE / 'links'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'index.html').write_text(html, encoding='utf-8')
    print(f"  links/index.html: {len(blues_sites)} live blues sites ({dead_count} dead filtered)")


# ── Postprocess & deploy ───────────────────────────────────────────────────────
def postprocess_dead_links():
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


def copy_root_files():
    for fname in ['_redirects', '_headers', 'robots.txt']:
        src = ARC / fname
        if src.exists():
            shutil.copy2(src, SITE / fname)

    tmpl = JINJA_ENV.get_template('404.html.j2')
    (SITE / '404.html').write_text(tmpl.render(), encoding='utf-8')

    print("  Root files: _redirects, _headers, 404.html")


# Export all names (including _private helpers) so 'from generate_shared import *' works
__all__ = [k for k in globals() if not k.startswith('__')]
