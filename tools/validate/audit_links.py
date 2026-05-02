#!/usr/bin/env python3
"""
Audit internal links in site/ and produce bluesru-arc/data/link_fixes.yaml.

For each internal <a href> in generated HTML:
  1. Apply existing redirect rules — if resolved, mark as OK
  2. Check if target exists in site/ filesystem — if yes, OK
  3. Otherwise: classify as broken, try to recover or mark dead

Output: bluesru-arc/data/link_fixes.yaml
  /path/to/dead/page: dead
  /path/old/location: /path/new/location

Run from the workspace root (parent of bluesru-arc/).
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ARC   = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
ROOT  = WORKSPACE
SITE  = WORKSPACE / "bluesru-site"
OUT   = ARC / "data" / "link_fixes.yaml"


# ── Load redirect rules (same logic as generate.py) ───────────────────────────

def load_redirect_rules():
    rules = []
    f = ARC / '_redirects'
    if not f.exists():
        return rules
    for line in f.read_text(encoding='utf-8').splitlines():
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
            target = dst.replace(':splat', '').rstrip('/')
            rules.append(('wildcard', prefix, target))
        elif '?' in src:
            path_part, qs = src.split('?', 1)
            rules.append(('query', path_part, qs, dst))
        else:
            rules.append(('exact', src, dst))
    return rules


def apply_redirect(href, rules):
    """Return redirect target or None if no rule matches."""
    path = href.split('?')[0].split('#')[0]
    for rule in rules:
        if rule[0] == 'exact' and rule[1] == path:
            return rule[2]
        elif rule[0] == 'wildcard':
            prefix = rule[1]
            if path.startswith(prefix + '/') or path == prefix:
                splat = path[len(prefix):].lstrip('/')
                target = rule[2]
                return (target.rstrip('/') + '/' + splat).rstrip('/') + '/'
        elif rule[0] == 'query' and rule[1] == path and '?' in href:
            qs = href.split('?')[1].split('#')[0]
            if rule[2] in qs:
                return rule[3]
    return None


MEDIA_EXTENSIONS = {'.mp3', '.ram', '.ogg', '.wav', '.mp4', '.avi', '.rm', '.flv', '.wma',
                    '.jpg', '.jpeg', '.gif', '.png', '.bmp', '.webp', '.tif', '.tiff',
                    '.zip', '.pdf', '.doc', '.docx', '.txt'}

def path_exists(path, site):
    """Check if a path resolves to a file in site/."""
    path = path.split('?')[0].split('#')[0]
    # Media files live in bluesru-media/, not in site/ — treat as OK
    ext = '.' + path.rsplit('.', 1)[-1].lower() if '.' in path.split('/')[-1] else ''
    if ext in MEDIA_EXTENSIONS:
        return True
    # /forum/topicN paths are served via rewrite rule — treat as OK
    import re as _re
    if _re.match(r'^/forum/topic\d+/?$', path):
        return True
    p = site / path.lstrip('/')
    if p.is_file():
        return True
    if p.is_dir() and (p / 'index.html').is_file():
        return True
    # Try with/without trailing slash
    if not path.endswith('/'):
        p2 = site / (path.lstrip('/') + '/')
        if p2.is_dir() and (p2 / 'index.html').is_file():
            return True
        # Try as .html file (e.g. /forum/page2 → page2.html)
        p3 = site / (path.lstrip('/') + '.html')
        if p3.is_file():
            return True
    return False


def normalize(href):
    """Normalize internal href for comparison."""
    path = href.split('?')[0].split('#')[0]
    path = re.sub(r'/index\.html?$', '/', path)
    if path and '.' not in path.split('/')[-1] and not path.endswith('/'):
        path += '/'
    return path


def collect_links(site):
    """Collect all (source_file, href) pairs from site/ HTML."""
    links = []
    for html_file in site.rglob('*.html'):
        try:
            content = html_file.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for m in re.finditer(r'href="(/[^"#?][^"]*)"', content):
            href = m.group(1)
            if href.startswith('//'):
                continue
            links.append((html_file, href))
    return links


def main():
    rules = load_redirect_rules()
    print(f"Loaded {len(rules)} redirect rules")

    links = collect_links(SITE)
    print(f"Found {len(links)} internal links across site/")

    # Deduplicate paths
    all_paths = set(normalize(href) for _, href in links)
    print(f"Unique paths: {len(all_paths)}")

    existing_fixes = {}
    if OUT.exists():
        existing_fixes = yaml.safe_load(OUT.read_text(encoding='utf-8')) or {}

    broken = {}     # path → set of source pages
    redirected = 0
    ok = 0

    for src_file, href in links:
        path = normalize(href)

        # Skip already-classified paths
        if path in existing_fixes:
            continue

        # Check redirect rules
        redirected_to = apply_redirect(path, rules)
        if redirected_to:
            redirected += 1
            continue

        # Check filesystem
        if path_exists(path, SITE):
            ok += 1
            continue

        # Broken
        broken.setdefault(path, set()).add(str(src_file.relative_to(SITE)))

    print(f"\nResults:")
    print(f"  Resolved by redirects: {redirected}")
    print(f"  Exists in site/:       {ok}")
    print(f"  Broken:                {len(broken)}")

    if not broken:
        print("No broken links found.")
        return

    # Try to auto-recover broken paths
    fixes = dict(existing_fixes)
    auto_fixed = 0
    dead_count = 0

    for path in sorted(broken):
        sources = broken[path]
        # Try common recovery patterns
        recovered = None

        # Old bluesmen URL patterns not caught by wildcard
        m = re.match(r'^/bluesmen/([^/]+)/?$', path)
        if m:
            slug = m.group(1).lower().replace('_', '-')
            candidate = f'/artist/{slug}/'
            if path_exists(candidate, SITE):
                recovered = candidate

        # /artist/{a_slug}/{a_slug}-{album_slug}/ → strip artist prefix
        if not recovered:
            m = re.match(r'^/artist/([^/]+)/([^/]+)/?$', path)
            if m:
                a_slug, full_slug = m.group(1), m.group(2)
                if full_slug.startswith(a_slug + '-'):
                    stripped = full_slug[len(a_slug) + 1:]
                    candidate = f'/artist/{a_slug}/{stripped}/'
                    if path_exists(candidate, SITE):
                        recovered = candidate

        # Old review paths
        if not recovered:
            m = re.match(r'^/review/(\d+)/?$', path)
            if m:
                # aspx-style numeric review — covered by _redirects already
                pass

        if recovered:
            fixes[path] = recovered
            auto_fixed += 1
            print(f"  AUTO-FIX: {path} → {recovered}")
        else:
            fixes[path] = 'dead'
            dead_count += 1

    print(f"\n  Auto-fixed: {auto_fixed}")
    print(f"  Marked dead: {dead_count}")

    # Show sample of dead links for review
    dead_paths = [p for p, v in fixes.items() if v == 'dead']
    print(f"\nSample dead links (first 30):")
    for p in sorted(dead_paths)[:30]:
        sample_sources = sorted(broken.get(p, set()))[:2]
        print(f"  {p}  (from: {', '.join(sample_sources[:2])})")

    # Write output
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        yaml.dump(fixes, allow_unicode=True, default_flow_style=False, sort_keys=True),
        encoding='utf-8')
    print(f"\nWritten: {OUT} ({len(fixes)} entries)")


if __name__ == '__main__':
    main()
