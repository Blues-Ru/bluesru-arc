#!/usr/bin/env python3
"""Generate /atb/ section — 'Весь этот блюз' radio show index + episode pages."""
import html as html_mod
import re
import sys
import yaml
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import (
    ATB,
    ATB_EPISODES_YAML,
    ATB_TRANSCRIPTS_DIR,
    CONTENT,
    FOOTER,
    JINJA_ENV,
    SITE,
    _parse_transcript_md,
    _transcript_to_html,
    process_html,
    read_file,
)


def generate_atb():
    print("Generating ATB (Весь этот блюз) section...")

    if not ATB_EPISODES_YAML.exists():
        print("  WARNING: data/atb/episodes.yaml not found. Run blues-dev/etl/extract_atb_mp3s.py first.")
        return

    episodes = yaml.safe_load(ATB_EPISODES_YAML.read_text(encoding='utf-8')) or []

    def _ep_summary(ep):
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

    ATB_SRC = ATB

    def _mp3_size_mb(ep):
        path = ep.get('path', '')
        if not path:
            return ''
        rel = path.lstrip('/')
        p = ATB_SRC / Path(rel).relative_to('atb')
        if not p.exists():
            return ''
        mb = p.stat().st_size / (1024 * 1024)
        return f'{mb:.0f} MB'

    SHOW_SUBDIRS_SET = {'', 'ATB2'}
    shows = episodes
    for show in shows:
        show['summary'] = _ep_summary(show)
        show['page_url'] = f"/atb/{show['slug']}/"
        show['is_show'] = (show.get('subdir') or '') in SHOW_SUBDIRS_SET
        for f in show.get('files', []):
            f['size_mb'] = _mp3_size_mb(f)

    by_date = OrderedDict()
    for show in shows:
        date = show.get('date', '') or 'unknown'
        by_date.setdefault(date, []).append(show)

    dated = [(d, shs) for d, shs in by_date.items() if d != 'unknown']
    dated.sort(key=lambda x: x[0], reverse=True)
    undated = by_date.get('unknown', [])

    year_groups = OrderedDict()
    for date_str, shs in dated:
        yr = date_str[:4]
        year_groups.setdefault(yr, []).append((date_str, shs))

    total = len(shows)

    # ── Episode pages ──────────────────────────────────────────────────────────
    ep_page_tmpl = JINJA_ENV.get_template('atb_episode.html.j2')

    def _format_desc(desc):
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

    def _load_transcripts(show):
        results = []
        for idx, f in enumerate(show.get('files', [])):
            stem = Path(f.get('filename', '')).stem
            if not stem:
                continue
            md_path = ATB_TRANSCRIPTS_DIR / f"{stem}.md"
            if not md_path.exists():
                results.append(None)
                continue
            md_text = md_path.read_text(encoding='utf-8')
            blocks = _parse_transcript_md(md_text)
            results.append(_transcript_to_html(blocks, idx) if blocks else None)
        return results

    def _artists_tags_html(show):
        tags = show.get('artists_tags') or []
        if not tags:
            return ''
        items = []
        for tag in tags:
            slug = tag.get('slug', '') if isinstance(tag, dict) else tag
            name = tag.get('name', slug) if isinstance(tag, dict) else slug
            if not slug:
                continue
            if (SITE / 'artist' / slug).is_dir():
                items.append(f'<a href="/artist/{slug}/">{html_mod.escape(name)}</a>')
            else:
                items.append(html_mod.escape(name))
        if not items:
            return ''
        return '<b>Музыканты:</b> ' + ' &middot; '.join(items)

    ep_pages_written = 0
    for show in shows:
        if not show.get('slug'):
            continue
        desc_html = _format_desc(show.get('description') or '')
        transcript_parts = _load_transcripts(show)
        transcripts_html = [h for h in transcript_parts if h]
        artists_html = _artists_tags_html(show)
        ep_dir = SITE / 'atb' / show['slug']
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / 'index.html').write_text(
            ep_page_tmpl.render(
                show=show,
                summary=show['summary'],
                description_html=desc_html,
                transcripts_html=transcripts_html,
                artists_tags_html=artists_html,
                multi_part=len(show.get('files', [])) > 1,
                footer=FOOTER,
            ), encoding='utf-8')
        ep_pages_written += 1

    # ── ATB index page ─────────────────────────────────────────────────────────
    tmpl = JINJA_ENV.get_template('atb_index.html.j2')
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

    # ── Old static ATB archive ─────────────────────────────────────────────────
    atb_content = CONTENT / 'atb'
    for candidate in ['ATBr-index2000.htm', 'index.htm', 'index.html', 'index.html.1', 'default.htm.1', 'default.html.1']:
        fallback = atb_content / candidate
        if fallback.exists():
            old_content = read_file(fallback)
            if old_content:
                old_content = process_html(old_content, atb_content, atb_content)
                old_content = re.sub(
                    r'(<img\b[^>]*\ssrc=")(?!https?://|/)([^"]+)(")',
                    r'\1../\2\3',
                    old_content, flags=re.IGNORECASE
                )
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


if __name__ == '__main__':
    generate_atb()
