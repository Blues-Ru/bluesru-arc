#!/usr/bin/env python3
"""Generate homepage (index.html) and links page."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from generate_shared import *


def generate_homepage():
    print("Generating homepage...")

    # ── Latest blues news ──────────────────────────────────────────────────────
    blues_news_items = []
    if NEWS_DIR.exists():
        raw_news = []
        for p in NEWS_DIR.rglob('*.md'):
            text = p.read_text(encoding='utf-8')
            m = RE_FM.match(text)
            if m:
                meta = yaml.safe_load(m.group(1))
                raw_news.append(meta)
        raw_news.sort(key=lambda x: str(x.get('date', '0000')), reverse=True)
        for meta in raw_news[:10]:
            ds = str(meta.get('date', ''))
            nid = meta.get('id', '')
            slug = meta.get('slug', f'story{nid}')
            url = (f'/news/{ds[:4]}/{ds[5:7]}/{ds[8:10]}/story{nid}/'
                   if ds and len(ds) >= 10 else '#')
            blues_news_items.append({
                'date': ds[:10] if ds else '',
                'title': meta.get('title', ''),
                'url': url,
            })

    # ── Latest ATB episodes ────────────────────────────────────────────────────
    latest_atb_items = []
    atb_yaml = DATA / 'atb' / 'episodes.yaml'
    if atb_yaml.exists():
        atb_shows = yaml.safe_load(atb_yaml.read_text(encoding='utf-8')) or []
        SHOW_SUBDIRS = {'', 'ATB2'}
        datable = [s for s in atb_shows if s.get('date') and s.get('date') != 'unknown'
                   and (s.get('subdir') or '') in SHOW_SUBDIRS]
        datable.sort(key=lambda s: s['date'], reverse=True)
        for s in datable[:8]:
            summary = s.get('summary') or ''
            if not summary:
                desc = re.sub(r'<[^>]+>', '', s.get('description') or '').strip()
                summary = desc[:160].rstrip() + ('…' if len(desc) > 160 else '') if desc else ''
            latest_atb_items.append({
                'date': s['date'],
                'summary': summary,
                'url': f"/atb/{s['slug']}/",
            })

    # ── Latest announcements ───────────────────────────────────────────────────
    latest_updates_items = []
    _atb_re_hp = re.compile(
        r'\bATB\b|atb_|/[Aa]tb/|Весь\s+[Ээ]тот\s+[Бб]люз', re.IGNORECASE)
    if ANNOUNCE_DIR.exists():
        raw_ann = []
        for p in sorted(ANNOUNCE_DIR.rglob('*.md')):
            text = p.read_text(encoding='utf-8')
            if _atb_re_hp.search(text):
                continue
            m = RE_FM.match(text)
            if m:
                meta = yaml.safe_load(m.group(1))
                body = m.group(2).strip()
                raw_ann.append((meta, body))
        raw_ann.sort(key=lambda x: str(x[0].get('date', '0000')), reverse=True)
        for meta, body in raw_ann[:8]:
            ds = str(meta.get('date', ''))
            latest_updates_items.append({
                'date': ds[:10] if ds else '',
                'html': body,
            })

    # ── Links ─────────────────────────────────────────────────────────────────
    links_yaml_path = DATA / 'links.yaml'
    links_html = ''
    if links_yaml_path.exists():
        links_data = yaml.safe_load(links_yaml_path.read_text(encoding='utf-8')) or {}
        categories = {c['id']: c for c in links_data.get('categories', [])}
        sites = links_data.get('sites', [])
        links_html = _build_links_snippet(categories, sites)
        _generate_links_page(categories, sites)

    # ── Render homepage ────────────────────────────────────────────────────────
    tmpl = JINJA_ENV.get_template('homepage.html.j2')
    html = tmpl.render(
        blues_news=blues_news_items,
        latest_atb=latest_atb_items,
        latest_updates=latest_updates_items,
        links_html=links_html,
        footer=FOOTER,
        today=datetime.now().strftime('%Y-%m-%d'),
    )
    (SITE / 'index.html').write_text(html, encoding='utf-8')
    print(f"  index.html: {len(blues_news_items)} blues news, {len(latest_atb_items)} ATB, {len(latest_updates_items)} updates")


if __name__ == '__main__':
    generate_homepage()
