#!/usr/bin/env python3
"""Generate XML sitemaps for blues.ru. Run as the final build step."""

import os
from datetime import date
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent
_site_default = str(ARC / 'bluesru-site') if os.environ.get('CF_PAGES') else str(ARC.parent / 'bluesru-site')
SITE = Path(os.environ.get('BLUESRU_SITE', _site_default))
BASE = 'https://blues.ru'
TODAY = date.today().isoformat()

# Top-level dirs that contain only assets, no indexable HTML
ASSET_DIRS = {'data', 'js', 'css', 'covers', 'images'}


def path_to_url(p: Path) -> str:
    parts = p.relative_to(SITE).parts
    if parts[-1] == 'index.html':
        return '/' if len(parts) == 1 else '/' + '/'.join(parts[:-1]) + '/'
    return '/' + '/'.join(parts)


def classify(url: str) -> str:
    if url.startswith('/forum/'):
        return 'forum'
    if url.startswith('/news/'):
        return 'news'
    if url.startswith('/calendar/') and url != '/calendar/':
        return 'calendar'
    return 'main'


def url_attrs(url: str) -> tuple:
    if url == '/':
        return 1.0, 'weekly'
    if url.startswith('/artist/'):
        return (0.8, 'monthly') if url.count('/') == 3 else (0.7, 'yearly')
    if url.startswith('/review/'):
        return 0.8, 'monthly'
    if url.startswith('/news/'):
        return (0.7, 'monthly') if url.count('/') <= 3 else (0.6, 'yearly')
    if url.startswith('/calendar/'):
        return 0.6, 'yearly'
    if url.startswith('/photo/') and url.count('/') >= 3:
        return 0.6, 'yearly'
    if url.startswith('/atb/') and url.count('/') >= 2:
        return 0.6, 'yearly'
    if url.startswith('/forum/topic'):
        return 0.3, 'yearly'
    if url.startswith('/forum/'):
        return 0.5, 'monthly'
    return 0.5, 'monthly'


def url_entry(url: str) -> str:
    priority, changefreq = url_attrs(url)
    return (
        f'  <url>\n'
        f'    <loc>{BASE}{url}</loc>\n'
        f'    <lastmod>{TODAY}</lastmod>\n'
        f'    <changefreq>{changefreq}</changefreq>\n'
        f'    <priority>{priority:.1f}</priority>\n'
        f'  </url>\n'
    )


def write_sitemap(path: Path, urls: list) -> int:
    with path.open('w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for url in sorted(urls):
            f.write(url_entry(url))
        f.write('</urlset>\n')
    print(f'  {path.name}: {len(urls)} URLs')
    return len(urls)


def write_index(path: Path, sitemap_names: list):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n',
    ]
    for name in sitemap_names:
        lines.append(
            f'  <sitemap>\n'
            f'    <loc>{BASE}/{name}</loc>\n'
            f'    <lastmod>{TODAY}</lastmod>\n'
            f'  </sitemap>\n'
        )
    lines.append('</sitemapindex>\n')
    path.write_text(''.join(lines), encoding='utf-8')
    print(f'  sitemap_index.xml: {len(sitemap_names)} sitemaps')


def collect_urls() -> dict:
    buckets: dict = {'main': [], 'news': [], 'calendar': [], 'forum': []}

    for p in SITE.rglob('*.html'):
        rel = p.relative_to(SITE)
        parts = rel.parts
        # Skip asset-only top-level dirs
        if parts[0] in ASSET_DIRS:
            continue
        # Skip images subdirs inside content dirs (news/images/, calendar/images/)
        if len(parts) >= 2 and parts[1] == 'images':
            continue

        url = path_to_url(p)
        buckets[classify(url)].append(url)

    return buckets


def main():
    print('Generating sitemaps...')
    if not SITE.exists():
        print(f'  ERROR: site not found at {SITE}')
        return

    buckets = collect_urls()
    sitemap_names = []

    for filename, urls in [
        ('sitemap_main.xml',     buckets['main']),
        ('sitemap_news.xml',     buckets['news']),
        ('sitemap_calendar.xml', buckets['calendar']),
        ('sitemap_forum.xml',    buckets['forum']),
    ]:
        if urls:
            write_sitemap(SITE / filename, urls)
            sitemap_names.append(filename)

    write_index(SITE / 'sitemap_index.xml', sitemap_names)


if __name__ == '__main__':
    main()
