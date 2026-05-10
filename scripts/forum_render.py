"""
Forum HTML rendering.

Renders forum posts, topics, and provides HTML sanitization for user content.
All state (spam IDs, author slugs) is passed in; no globals.
"""

from __future__ import annotations

import html as html_mod
import re
import urllib.parse
from datetime import datetime

from models import ForumPost


# ── Allowed HTML tags in forum posts ─────────────────────────────────────────
_ALLOWED_TAGS = {'b', 'i', 'u', 'strong', 'em', 'br', 's', 'strike'}
_RE_TAG       = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)
_RE_HREF      = re.compile(r'\bhref\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
_RE_VIDEO_SRC = re.compile(
    r'\bsrc\s*=\s*["\']([^"\']*(?:youtube\.com|youtu\.be|vimeo\.com)[^"\']*)["\']',
    re.IGNORECASE)
_RE_NUMERIC_REF = re.compile(r'&#\d+;')
_RE_BARE_URL    = re.compile(r'(?<!["\'>])(https?://[^\s<>"\']+)', re.IGNORECASE)


# ── Sanitization ──────────────────────────────────────────────────────────────

def _escape_preserving_refs(text: str) -> str:
    refs = _RE_NUMERIC_REF.findall(text)
    placeholder_map: dict[str, str] = {}
    for i, ref in enumerate(refs):
        key = f'\x00REF{i}\x00'
        placeholder_map[key] = ref
        text = text.replace(ref, key, 1)
    text = html_mod.escape(text)
    for key, ref in placeholder_map.items():
        text = text.replace(html_mod.escape(key), ref)
    return text


def sanitize_forum_html(text: str) -> str:
    """Whitelist-sanitize user forum HTML: allow b/i/u/a/iframe(youtube only)."""
    result: list[str] = []
    pos = 0
    for m in _RE_TAG.finditer(text):
        result.append(_escape_preserving_refs(text[pos:m.start()]))
        pos = m.end()
        closing, tag, attrs_raw = m.group(1), m.group(2).lower(), m.group(3)
        if tag in _ALLOWED_TAGS:
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
                    f'frameborder="0" allowfullscreen></iframe>')
    result.append(_escape_preserving_refs(text[pos:]))
    return ''.join(result)


def autolink_bare_urls(html_text: str) -> str:
    """Wrap bare http URLs in <a> tags (skipping already-linked text)."""
    def replace_url(m: re.Match) -> str:
        url = m.group(1).rstrip('.,;:!?)\'\"')
        trailing = m.group(1)[len(url):]
        return f'<a href="{url}" rel="nofollow">{url}</a>{trailing}'
    return _RE_BARE_URL.sub(replace_url, html_text)


# ── Date formatting ────────────────────────────────────────────────────────────

def format_forum_date(date_str: str | None) -> str:
    if not date_str:
        return ''
    s = str(date_str)
    try:
        if len(s) >= 16 and s[10] == ' ':
            return datetime.strptime(s[:16], '%Y-%m-%d %H:%M').strftime('%d.%m.%y %H:%M')
        return datetime.strptime(s[:10], '%Y-%m-%d').strftime('%d.%m.%y')
    except Exception:
        return s


# ── Poster linking ────────────────────────────────────────────────────────────

def poster_html(raw_poster: str, author_slugs: dict[str, str]) -> str:
    """Wrap poster name in a link to their author page or search."""
    escaped = html_mod.escape(raw_poster)
    slug = author_slugs.get(raw_poster, '')
    if slug:
        return f'<a href="/forum/{slug}/" class="forum-author">{escaped}</a>'
    if raw_poster:
        q = urllib.parse.quote(raw_poster, safe='')
        return f'<a href="/forum/authors/?q={q}" class="forum-author">{escaped}</a>'
    return escaped


# ── Post / topic HTML ─────────────────────────────────────────────────────────

def render_post_html(
    post: dict,
    topic_slug: str,
    full: bool = True,
    depth: int = 0,
    spam_ids: set[int] | None = None,
    author_slugs: dict[str, str] | None = None,
) -> str:
    spam_ids     = spam_ids or set()
    author_slugs = author_slugs or {}

    pid = post.get('id', '')
    if pid in spam_ids:
        return ''

    raw_poster = post.get('poster', '') or ''
    poster     = poster_html(raw_poster, author_slugs)
    date_str   = format_forum_date(post.get('date', ''))
    subject    = html_mod.escape(post.get('subject', '') or '')
    text       = post.get('text', '') or ''
    deleted    = post.get('deleted', False)
    replies    = post.get('replies', [])

    def _render_replies(d: int) -> str:
        return ''.join(
            render_post_html(r, topic_slug, full=full, depth=d,
                             spam_ids=spam_ids, author_slugs=author_slugs)
            for r in replies)

    if deleted:
        text_html = ''
    else:
        sanitized = sanitize_forum_html(text)
        sanitized = autolink_bare_urls(sanitized)
        sanitized = re.sub(r'\n', '</p><p>', sanitized)
        text_html = f'<p>{sanitized}</p>' if text else ''

    if full and depth == 0:
        html = f'<div class="message"><a name="post{pid}"></a>'
        if text_html:
            html += f'<div class="text">{text_html}</div>'
        html += _render_replies(1)
        html += '</div>'
        return html

    if full:
        if deleted:
            return _render_replies(depth + 1)
        html = (f'<div class="message"><a name="post{pid}"></a>'
                f'<div class="header">'
                f'<img class="bullet" src="/forum/bullet.gif" id="bullet{pid}">'
                f'<span class="subject">{subject}</span>'
                f'\n    - <span class="name">{poster}</span>'
                f'\n      <span class="date">({date_str})</span>'
                f'\n      <span class="self-link"><a href="/forum/{topic_slug}#post{pid}">#</a></span>'
                f'</div>')
        if text_html:
            html += f'<div class="text">{text_html}</div>'
        html += _render_replies(depth + 1)
        html += '</div>'
        return html

    # summary (index) view
    if deleted:
        return _render_replies(depth + 1)
    html = (f'<div class="message"><a name="post{pid}"></a>'
            f'<div class="header">'
            f'<img class="bullet" src="/forum/bullet.gif" id="bullet{pid}">'
            f'<span class="subject"><a href="/forum/{topic_slug}">{subject}</a></span>'
            f'\n    - <span class="name">{poster}</span>'
            f'\n      <span class="date">({date_str})</span>'
            f'</div>')
    html += _render_replies(depth + 1)
    html += '</div>'
    return html


def render_topic_html(
    topic_data: dict | None,
    topic_meta: dict,
    full: bool = False,
    forum_page: int = 1,
    spam_ids: set[int] | None = None,
    author_slugs: dict[str, str] | None = None,
) -> str:
    spam_ids     = spam_ids or set()
    author_slugs = author_slugs or {}

    topic_id = topic_meta.get('topic_id', '')
    slug = f'topic{topic_id}' if topic_id else topic_meta.get('slug', f'topic-{topic_id}')
    posts = topic_data.get('posts', []) if topic_data else []

    if not posts:
        return ''

    if full:
        first = posts[0]
        raw_fp = first.get('poster', '') or ''
        first_poster = poster_html(html_mod.escape(raw_fp), author_slugs)
        first_date   = format_forum_date(first.get('date', ''))
        subject = html_mod.escape(
            posts[0].get('subject', '') or topic_meta.get('title', '') or '')

        page_url  = '/forum/' if forum_page <= 1 else f'/forum/page{forum_page}'
        forum_back = f'{page_url}#topic{topic_id}'
        html = (f'<div class="topic-header">'
                f'<a href="{forum_back}">Blues.Ru &rsaquo; Форум</a> &rsaquo;\n'
                f'  <span class="subject">{subject}</span>\n'
                f'    &mdash; <span class="name">{first_poster}</span>\n'
                f'      <span class="date">({first_date})</span>'
                f'</div>')
        html += f'<div class="topic"><a name="topic{topic_id}"></a>'
        for post in posts:
            html += render_post_html(post, slug, full=True,
                                     spam_ids=spam_ids, author_slugs=author_slugs)
        html += '</div>'
    else:
        html = f'<div class="topic"><a name="topic{topic_id}"></a>'
        for post in posts:
            html += render_post_html(post, slug, full=False,
                                     spam_ids=spam_ids, author_slugs=author_slugs)
        html += '</div>'

    return html


def topic_is_all_deleted(
    topic_data: dict | None,
    spam_ids: set[int] | None = None,
) -> bool:
    spam_ids = spam_ids or set()

    def has_visible(posts: list) -> bool:
        for p in posts:
            pid = p.get('id')
            if pid in spam_ids:
                continue
            if not p.get('deleted', False):
                return True
            if has_visible(p.get('replies', [])):
                return True
        return False

    if topic_data is None:
        return True
    return not has_visible(topic_data.get('posts', []))
