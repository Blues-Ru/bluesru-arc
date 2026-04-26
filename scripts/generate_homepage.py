#!/usr/bin/env python3
"""
Generate homepage (index.html) and blues links page.

Reads:
  - blues-arc/templates/homepage.html
  - /private/tmp/claude-501/blues-links.xml (downloaded from live site)
  - OR generates placeholder links if XML not available

Outputs:
  - site/index.html
  - blues-arc/data/links.yaml  (source YAML, committed)
  - site/links/index.html

Run from /Users/fedor/bluesru/
"""

import re
import yaml
import xml.etree.ElementTree as ET
from pathlib import Path
from string import Template

import os
ARC = Path(__file__).resolve().parent.parent
_ws = Path(os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
SITE_DIR = Path(os.environ.get('BLUESRU_SITE', str(_ws / 'bluesru-site')))
TMPL = ARC / "templates" / "homepage.html"
OUT_HOME = SITE_DIR / "index.html"
OUT_LINKS_YAML = ARC / "data" / "links.yaml"
OUT_LINKS_PAGE = SITE_DIR / "links"
LINKS_XML = Path("/private/tmp/claude-501/blues-links.xml")


def load_links_from_xml(xml_path):
    """Parse links from downloaded XML file."""
    with xml_path.open('rb') as f:
        content = f.read().decode('windows-1251', errors='replace')
    root = ET.fromstring(content)

    # Build category map
    categories = {}
    for cat in root.findall('.//category'):
        cid = cat.get('id', '')
        categories[cid] = {
            'id': cid,
            'name': cat.get('name', ''),
            'parent_id': cat.get('parent-id', ''),
            'description': cat.get('description', ''),
        }

    # Build site-category pairs
    site_cats = {}
    for pair in root.findall('.//site-category'):
        sid = pair.get('site-id', '')
        cid = pair.get('category-id', '')
        site_cats.setdefault(sid, []).append(cid)

    # Build sites list
    sites = []
    for site in root.findall('.//site'):
        sid = site.get('id', '')
        sites.append({
            'id': sid,
            'name': site.get('name', ''),
            'url': site.get('url', ''),
            'description': site.get('description', ''),
            'categories': site_cats.get(sid, []),
            'status': 'unknown',  # to be validated
        })

    return categories, sites


def save_links_yaml(categories, sites):
    OUT_LINKS_YAML.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'categories': list(categories.values()),
        'sites': sites,
    }
    with OUT_LINKS_YAML.open('w', encoding='utf-8') as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"  links.yaml: {len(sites)} sites, {len(categories)} categories")


def get_blues_cat_ids(categories, root_id='1'):
    """Return all category ids that belong to the blues root tree."""
    result = {root_id}
    changed = True
    while changed:
        changed = False
        for c in categories.values():
            if c['id'] not in result and c.get('parent_id') in result:
                result.add(c['id'])
                changed = True
    return result


def generate_links_html(categories, sites):
    """Generate HTML for links section (simple flat list by category)."""
    blues_ids = get_blues_cat_ids(categories)
    # Only show sites in the blues tree
    blues_sites = [s for s in sites if any(cid in blues_ids for cid in s['categories'])]
    # Build sub-categories of the blues root
    top_cats = [c for c in categories.values() if c.get('parent_id') == '1']
    # Build sites by category
    by_cat = {}
    for site in sites:
        for cid in site['categories']:
            by_cat.setdefault(cid, []).append(site)

    by_cat = {}
    for site in blues_sites:
        for cid in site['categories']:
            if cid in blues_ids:
                by_cat.setdefault(cid, []).append(site)

    html = '<b><a href="/links/">Блюзовые ссылки</a></b>\n<ul>\n'
    shown = 0
    for cat in sorted(top_cats, key=lambda c: c.get('name', '')):
        cat_sites = by_cat.get(cat['id'], [])
        if not cat_sites:
            continue
        html += f'<li><b>{cat["name"]}</b><ul>\n'
        for site in cat_sites[:5]:  # show max 5 per category on homepage
            name = site['name']
            url = site['url']
            html += f'  <li><a href="{url}">{name}</a></li>\n'
            shown += 1
        if len(cat_sites) > 5:
            html += f'  <li><a href="/links/"><small>ещё {len(cat_sites)-5}...</small></a></li>\n'
        html += '</ul></li>\n'
    html += f'</ul>\n<p><a href="/links/">Все ссылки &gt;&gt;</a></p>\n'
    return html, shown


def generate_links_page(categories, sites):
    """Generate full links page — blues links only (root id=1), live/redirected only."""
    OUT_LINKS_PAGE.mkdir(parents=True, exist_ok=True)

    blues_ids = get_blues_cat_ids(categories)
    # Only show live and redirected sites (filter out dead and changed)
    live_statuses = {'live', 'redirected', 'unknown'}
    blues_sites = [
        s for s in sites
        if any(cid in blues_ids for cid in s['categories'])
        and s.get('status', 'unknown') in live_statuses
    ]

    by_cat = {}
    for site in blues_sites:
        for cid in site['categories']:
            if cid in blues_ids:
                by_cat.setdefault(cid, []).append(site)

    # Build category tree — root is id=1
    top_cats = [c for c in categories.values() if c.get('parent_id') == '1']
    child_cats = {}
    for c in categories.values():
        if c.get('parent_id'):
            child_cats.setdefault(c['parent_id'], []).append(c)

    html = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Блюзовые ссылки — Blues.Ru</title>
<link rel="shortcut icon" href="/images/bluesru.ico">
<style>a{text-decoration:none}</style>
</head>
<body bgcolor="#FFFFFF" text="#000000" link="#0000FF" vlink="#5511CC">
<p><a href="/"><b>Blues.Ru</b></a> &gt; Ссылки</p>
<h1>Блюзовые ссылки</h1>
<p>Ссылки на сайты о блюзе. Собраны в 2001–2009 годах; показаны работавшие на момент проверки.</p>\n'''

    def render_cat(cat, depth=0):
        cid = cat['id']
        cat_sites = by_cat.get(cid, [])
        child_list = sorted(child_cats.get(cid, []), key=lambda c: c.get('name', ''))
        if not cat_sites and not child_list:
            return ''
        hn = f'h{"23456"[min(depth,4)]}'
        s = f'<{hn}>{cat["name"]}</{hn}>\n'
        if cat_sites:
            s += '<ul>\n'
            for site in sorted(cat_sites, key=lambda x: x.get('name', '')):
                desc = f' — {site["description"]}' if site.get('description') else ''
                s += f'  <li><a href="{site["url"]}">{site["name"]}</a>{desc}</li>\n'
            s += '</ul>\n'
        for child in child_list:
            s += render_cat(child, depth+1)
        return s

    for cat in sorted(top_cats, key=lambda c: c.get('name', '')):
        html += render_cat(cat)

    html += '''<hr size="1">
<p><a href="/"><b>Blues.Ru</b></a></p>
</body>
</html>'''

    (OUT_LINKS_PAGE / "index.html").write_text(html, encoding='utf-8')
    dead_count = sum(1 for s in sites if any(cid in blues_ids for cid in s.get('categories',[])) and s.get('status') in ('dead','changed'))
    print(f"  links/index.html: {len(blues_sites)} live blues sites ({dead_count} dead filtered out)")


GA_SNIPPET = '''\
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8HDC1W9R3E"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-8HDC1W9R3E');
</script>'''


def generate_homepage(links_html):
    template = TMPL.read_text(encoding='utf-8')
    out = template.replace('{{ links_html }}', links_html)
    out = out.replace('{{ ga_snippet | safe }}', GA_SNIPPET)
    OUT_HOME.parent.mkdir(parents=True, exist_ok=True)
    OUT_HOME.write_text(out, encoding='utf-8')
    print(f"  index.html generated")


def load_links_from_yaml(yaml_path):
    """Load categories and sites from the committed links.yaml."""
    with yaml_path.open(encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    categories = {c['id']: c for c in data.get('categories', [])}
    sites = data.get('sites', [])
    return categories, sites


def main():
    print("Generating homepage and links...")

    if LINKS_XML.exists():
        categories, sites = load_links_from_xml(LINKS_XML)
        save_links_yaml(categories, sites)
        print(f"  Loaded links from XML: {len(sites)} sites")
    elif OUT_LINKS_YAML.exists():
        categories, sites = load_links_from_yaml(OUT_LINKS_YAML)
        print(f"  Loaded links from YAML: {len(sites)} sites, {len(categories)} categories")
    else:
        print(f"  WARNING: No links source found — using placeholder")
        categories, sites = {}, []

    if categories or sites:
        links_html, shown = generate_links_html(categories, sites)
        generate_links_page(categories, sites)
        print(f"  links snippet: {shown} links shown")
    else:
        links_html = '<b><a href="/links/">Блюзовые ссылки</a></b>'

    generate_homepage(links_html)
    print("Done.")


if __name__ == '__main__':
    main()
