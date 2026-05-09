#!/usr/bin/env python3
"""Generate /news/ section pages."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from generate_shared import *
from collections import defaultdict, OrderedDict as _OD


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
        body = body.strip()
        if not body:
            return body
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
                    prev_lower = prev.lower().rstrip()
                    part_lower = part.lower()
                    if prev_lower.endswith('</p>') or part_lower.startswith('<p>'):
                        joined.append(part)
                    else:
                        joined[-1] = prev + '</p><p>' + part
                        continue
                joined.append(part)
            body = '\n'.join(joined)
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
        image_path = None
        if nid:
            for ext in ('.jpg', '.gif', '.png'):
                if (ARC / 'news' / 'images' / f'{nid}{ext}').exists():
                    image_path = f'/news/images/{nid}{ext}'
                    break
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
            'image_path': image_path,
        }

    all_items = [make_news_item(meta, body) for meta, body in items]

    by_month = defaultdict(list)
    for item in all_items:
        ds = item['date_str']
        if ds and len(ds) >= 7:
            by_month[ds[:7]].append(item)
    month_keys_sorted = sorted(by_month.keys(), reverse=True)

    years_arch = _OD()
    for mk in month_keys_sorted:
        yr = mk[:4]
        y2, m2 = mk[:4], int(mk[5:7])
        years_arch.setdefault(yr, []).append({
            'key': mk,
            'url': f'/news/{y2}/{m2:02d}/',
            'month_ru': MONTHS_RU[m2],
            'count': len(by_month[mk]),
        })
    year_keys_desc = list(years_arch.keys())

    def _years_footer(current_yr=None):
        links = []
        for y in year_keys_desc:
            if y == current_yr:
                links.append(f'<b>{y}</b>')
            else:
                links.append(f'<a href="/news/{y}/">{y}</a>')
        return ' | '.join(links)

    # /news/ — 10 latest
    if len(all_items) > 10:
        ds11 = all_items[10]['date_str']
        arch_yr, arch_mo = ds11[:4], int(ds11[5:7])
        bottom_nav_html = f'<a href="/news/{arch_yr}/{arch_mo:02d}/">{arch_yr} {MONTHS_RU[arch_mo]} →</a>'
    elif year_keys_desc:
        bottom_nav_html = f'<a href="/news/{year_keys_desc[0]}/">{year_keys_desc[0]} →</a>'
    else:
        bottom_nav_html = ''

    dst = SITE / 'news' / 'index.html'
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(tmpl.render(
        news_items=all_items[:10],
        page_title='Блюзовые новости',
        nav_links=None,
        bottom_nav=bottom_nav_html,
        footer=FOOTER,
        canonical_url='https://blues.ru/news/',
    ), encoding='utf-8')

    # /news/YYYY/MM/ — monthly archive pages
    month_keys_asc = sorted(by_month.keys())
    monthly_count = 0
    for i, key in enumerate(month_keys_asc):
        year, mo = key[:4], int(key[5:7])
        prev_key = month_keys_asc[i - 1] if i > 0 else None
        next_key = month_keys_asc[i + 1] if i + 1 < len(month_keys_asc) else None

        def month_nav(k):
            if not k:
                return ''
            y2, m2 = k[:4], int(k[5:7])
            return f'<a href="/news/{y2}/{m2:02d}/">{y2} {MONTHS_RU[m2]}</a>'

        crumb = (f'<h2><a href="/">Blues.Ru</a> &gt; '
                 f'<a href="/news/">Новости</a> &gt; '
                 f'<a href="/news/{year}/">{year}</a> &gt; '
                 f'{MONTHS_RU[mo]}</h2>')
        pager_parts = []
        if next_key:
            pager_parts.append(f'← {month_nav(next_key)}')
        if prev_key:
            pager_parts.append(f'{month_nav(prev_key)} →')
        pager = ' | '.join(pager_parts)
        top_nav = crumb + (f'<p>{pager}</p>' if pager else '')
        bot_nav = pager

        dst_month = SITE / 'news' / year / f'{mo:02d}' / 'index.html'
        dst_month.parent.mkdir(parents=True, exist_ok=True)
        dst_month.write_text(tmpl.render(
            news_items=by_month[key],
            page_title=f'Блюзовые новости: {year} {MONTHS_RU[mo]}',
            nav_links=top_nav,
            bottom_nav=bot_nav,
            footer=FOOTER,
        ), encoding='utf-8')
        monthly_count += 1

    # /news/YYYY/MM/DD/storyN/ — individual story pages
    dated_items = [it for it in all_items if it['date_str'] and len(it['date_str']) >= 10]
    story_tmpl = JINJA_ENV.get_template('news_list.html.j2')
    story_count = 0
    for idx, item in enumerate(dated_items):
        ds = item['date_str']
        year, mo_str, day = ds[:4], ds[5:7], ds[8:10]
        mo_int = int(mo_str)
        nid = item['id']
        dst_story = SITE / 'news' / year / mo_str / day / f'story{nid}' / 'index.html'
        dst_story.parent.mkdir(parents=True, exist_ok=True)

        prev_item = dated_items[idx + 1] if idx + 1 < len(dated_items) else None
        next_item = dated_items[idx - 1] if idx > 0 else None

        def story_link(it):
            return f'<a href="{it["url"]}">{it["date_display"]}</a>'

        crumb = (f'<a href="/news/">Новости</a> : '
                 f'<a href="/news/{year}/">{year}</a> : '
                 f'<a href="/news/{year}/{mo_str}/">{MONTHS_RU[mo_int]}</a>')
        pager_parts = []
        if next_item:
            pager_parts.append(f'← {story_link(next_item)}')
        if prev_item:
            pager_parts.append(f'{story_link(prev_item)} →')
        pager = ' | '.join(pager_parts)
        # For single story: crumb on first line, pager (nav dates) on second
        top_nav = crumb + (f'<br><span style="color:#4F62B5">{pager}</span>' if pager else '')
        bot_nav = pager if pager else crumb

        dst_story.write_text(story_tmpl.render(
            news_items=[item],
            page_title=item['title'] or f'Новость {nid}',
            nav_links=top_nav,
            bottom_nav=bot_nav,
            single_story=True,
            footer=FOOTER,
        ), encoding='utf-8')
        story_count += 1

    print(f"  News: {len(all_items)} items, {monthly_count} monthly pages, {story_count} story pages")

    # /news/YYYY/ — year index with month sections
    year_archive_count = 0
    for i, yr in enumerate(year_keys_desc):
        prev_yr = year_keys_desc[i + 1] if i + 1 < len(year_keys_desc) else None
        next_yr = year_keys_desc[i - 1] if i > 0 else None

        crumb = f'<h2><a href="/">Blues.Ru</a> &gt; <a href="/news/">Новости</a> &gt; {yr}</h2>'
        pager_parts = []
        if next_yr:
            pager_parts.append(f'← <a href="/news/{next_yr}/">{next_yr}</a>')
        if prev_yr:
            pager_parts.append(f'<a href="/news/{prev_yr}/">{prev_yr}</a> →')
        pager = ' | '.join(pager_parts)
        year_nav = crumb + (f'<p>{pager}</p>' if pager else '')

        year_items_html = []
        for m in years_arch[yr]:
            mo_int = int(m['key'][5:7])
            items_in_month = by_month[m['key']]
            ul_items = ''.join(
                f'<li><font color="#4F62B5">{it["date_display"]}</font> '
                f'<a href="{it["url"]}">{it["title"] or ("Новость " + str(it["id"]))}</a></li>\n'
                for it in items_in_month
            )
            year_items_html.append(
                f'<h3><a href="{m["url"]}">{yr} {MONTHS_RU[mo_int]}</a> ({m["count"]})</h3>\n'
                f'<ul>\n{ul_items}</ul>'
            )
        body_html = '\n'.join(year_items_html)
        years_foot = _years_footer(yr)
        bot_nav = (pager + '<br><br>' if pager else '') + years_foot

        yr_dst = SITE / 'news' / yr / 'index.html'
        yr_dst.parent.mkdir(parents=True, exist_ok=True)
        yr_dst.write_text(tmpl.render(
            news_items=[],
            year_body=body_html,
            page_title=f'Блюзовые новости {yr}',
            nav_links=year_nav,
            bottom_nav=bot_nav,
            footer=FOOTER,
        ), encoding='utf-8')
        year_archive_count += 1

    print(f"  Archive: {year_archive_count} year pages")


if __name__ == '__main__':
    generate_news()
