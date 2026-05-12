"""
HTML processing utilities: analytics stripping, SSI resolution, link rewriting.

All functions are pure (no global side effects).  Import what you need.
"""

from __future__ import annotations

import html as html_mod
import re
from pathlib import Path
from typing import Optional

import yaml

# ── Path constants (needed for footer/include resolution) ─────────────────────
_ARC = Path(__file__).resolve().parent.parent
_INCLUDES = _ARC / 'includes'
_CONTENT  = _ARC / 'content'

# ── Analytics / ads patterns ──────────────────────────────────────────────────
_ANALYTICS_PATTERNS = [
    re.compile(r'<!--\s*LiveInternet.*?//-->', re.IGNORECASE | re.DOTALL),
    re.compile(
        r'<script[^>]*>[\s\S]*?(?:liveinternet|counter\.yadro|spylog|rambler\.ru/top100)[\s\S]*?</script>',
        re.IGNORECASE),
    re.compile(r'<img[^>]*(?:counter\.rambler|top100\.cnt)[^>]*>', re.IGNORECASE),
    re.compile(r'<noscript[^>]*>[\s\S]*?top100[\s\S]*?</noscript>', re.IGNORECASE),
    re.compile(r'<!-- Yandex\.Metrika -->.*?<!-- /Yandex\.Metrika -->', re.IGNORECASE | re.DOTALL),
    re.compile(r'<!-- Google\.Analytics -->.*?<!-- /Google\.Analytics -->', re.IGNORECASE | re.DOTALL),
]
_AD_SCRIPTS = re.compile(r'<script[^>]*(?:bluesad|googleapis)[^>]*></script>', re.IGNORECASE)

# ── SSI patterns ──────────────────────────────────────────────────────────────
RE_INCLUDE_VIRTUAL = re.compile(r'<\\?!--#include\s+virtual\s*=\s*"([^"]+)"\s*-->', re.IGNORECASE)
RE_INCLUDE_FILE    = re.compile(r'<\\?!--#include\s+file\s*=\s*"([^"]+)"\s*-->', re.IGNORECASE)
RE_DYNAMIC_ASPX    = re.compile(r'<\\?!--#include\s+virtual\s*=\s*"/data/dynamic\.aspx"\s*-->', re.IGNORECASE)
RE_UNRESOLVED      = re.compile(r'<!--\s*virtual include not resolved:\s*[^-]+?-->', re.IGNORECASE)

# ── Drop lists ────────────────────────────────────────────────────────────────
_DROP_INCLUDES = {
    '/liveinternetsmall.inc', '/liveinternet.inc', '/banner.inc',
    '/translate.inc', '/fedor/spylog.inc', '/reading/logoadv.inc',
    '/style/logoadv.inc',
}
_DROP_KEYWORDS = ['liveinternet', 'spylog', 'logoadv', 'banner.inc', 'translate.inc']

SKIP_EXTENSIONS = {
    '.mp3', '.ram', '.rm', '.swf', '.wma', '.wav',
    '.aspx', '.ascx', '.asp', '.xsl', '.cs', '.vb',
    '.sln', '.csproj', '.resx', '.config',
}

# ── Domain rewrite ────────────────────────────────────────────────────────────
_RE_BLUES_RU_DOMAIN = re.compile(
    r'^https?://(?:www\.)?(?:blues\.ru|a\.blues\.ru)(/.*)$', re.IGNORECASE
)


# ── Core HTML utilities ───────────────────────────────────────────────────────

def read_file(path: Path) -> Optional[str]:
    """Read a file trying UTF-8, windows-1251, latin-1 in order."""
    for enc in ('utf-8', 'windows-1251', 'latin-1'):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return None


def strip_analytics(content: str) -> str:
    """Remove tracking scripts, ads, and ASP.NET tags from HTML."""
    for pat in _ANALYTICS_PATTERNS:
        content = pat.sub('', content)
    content = _AD_SCRIPTS.sub('', content)
    content = re.sub(r'<%.*?%>', '', content, flags=re.DOTALL)
    content = re.sub(r'<asp:[^>]*/>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'<asp:Content\b[^>]*>(.*?)</asp:Content>', r'\1',
                     content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<asp:[^>]*>.*?</asp:[^>]*>', '',
                     content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a\b[^>]*allmusic\.com[^>]*>.*?</a>', '',
        content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a\b[^>]*href="[^"]*\.(?:ra|rm|ram)"[^>]*>\s*<img[^>]*ra\.gif[^>]*/?>\s*</a>',
        '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(
        r'<a\b[^>]*href="[^"]*\.ram"[^>]*>[^<]*</a>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'<img\b[^>]*ra\.gif[^>]*/?>', '', content, flags=re.IGNORECASE)
    return content


def normalize_filename(name: str) -> str:
    """Map legacy index names to index.html."""
    if name.lower() in ('default.htm', 'default.html', 'index.htm'):
        return 'index.html'
    return name


def resolve_include(
    vpath: str,
    source_dir: Path,
    source_root: Path,
    footer: str = '',
    donate: str = '',
) -> str:
    """Resolve a single SSI include directive, returning the included text."""
    vpath_lower = vpath.strip().lower()
    if vpath_lower == '/footer.inc':
        return footer
    if vpath_lower == '/donate.inc':
        return donate
    if vpath_lower in _DROP_INCLUDES or any(kw in vpath_lower for kw in _DROP_KEYWORDS):
        return ''
    if '/data/dynamic.aspx' in vpath_lower:
        return ''

    if vpath_lower.startswith('/'):
        rel = vpath.lstrip('/')
        candidates = [_INCLUDES / rel, _CONTENT / rel, source_root / rel]
    else:
        candidates = [source_dir / vpath, source_root / vpath]

    for disk_path in candidates:
        if disk_path.exists() and disk_path.is_file():
            content = read_file(disk_path)
            if content is None:
                continue
            content = strip_analytics(content)
            content = RE_INCLUDE_VIRTUAL.sub(
                lambda m: resolve_include(m.group(1), disk_path.parent, source_root,
                                          footer=footer, donate=donate),
                content)
            content = RE_INCLUDE_FILE.sub(
                lambda m: resolve_include(m.group(1), disk_path.parent, source_root,
                                          footer=footer, donate=donate),
                content)
            content = RE_DYNAMIC_ASPX.sub('', content)
            return content
    return ''


def rewrite_gallery_img_src(html_content: str, media_base_url: str) -> str:
    """Rewrite relative img src/href to absolute media base URL in gallery pages."""
    img_exts = r'(?i)\.(jpg|jpeg|png|gif|bmp|webp)'

    def rewrite_attr(m: re.Match) -> str:
        attr, quote, val = m.group(1), m.group(2), m.group(3)
        if val.startswith(('http://', 'https://', '/', '#', 'mailto:', 'javascript:')):
            return m.group(0)
        if re.search(img_exts, val.split('?')[0].split('#')[0]):
            clean = val.lstrip('./')
            return f'{attr}={quote}{media_base_url}/{clean}{quote}'
        return m.group(0)

    return re.compile(r'(src|href)=(["\'])([^"\']+)\2', re.IGNORECASE).sub(
        rewrite_attr, html_content)


# ── Link rewriting ─────────────────────────────────────────────────────────────

def make_link_rewriter(redirect_rules: list, link_fixes: dict):
    """
    Return a function ``rewrite_links(content) -> content`` that applies
    redirect rules and dead-link fixes to all internal hrefs in HTML.

    Separating rule loading from application keeps tests simple and avoids
    the module-level global state of the old generate_shared.py.
    """
    def _apply_redirect(href: str) -> str:
        if not href or not href.startswith('/') or href.startswith('//'):
            return href
        href = re.sub(r'/index\.html?$', '/', href)
        path_part = href.split('?')[0].split('#')[0]
        if path_part and '.' not in path_part.split('/')[-1]:
            if not path_part.endswith('/') and not re.match(r'^/forum/(topic|page)\d+$', path_part):
                href = path_part + '/' + (href[len(path_part):] if len(href) > len(path_part) else '')
        path = href.split('?')[0].split('#')[0]
        for rule in redirect_rules:
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

    def rewrite_links(content: str) -> str:
        def _rewrite_atag(m: re.Match) -> str:
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
            fix = link_fixes.get(path_key) or link_fixes.get(path_key + '/')
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

    return rewrite_links


def load_redirect_rules(redirects_file: Path) -> list:
    """Parse a Cloudflare _redirects file into a list of rule tuples."""
    rules = []
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


def load_link_fixes(fixes_path: Path) -> dict:
    if fixes_path.exists():
        return yaml.safe_load(fixes_path.read_text(encoding='utf-8')) or {}
    return {}
