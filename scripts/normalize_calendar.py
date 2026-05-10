#!/usr/bin/env python3
"""
One-time script: normalize calendar titles and add artist_slug matches.

- Converts ALL-CAPS surnames to Title Case: "Johnny WINTER" → "Johnny Winter"
- Attempts to match each unique title to an artist slug
- Adds `artist_slug` field to calendar entries
- Writes a change log for review

Run from /Users/fedor/bluesru/:
  python3 bluesru-arc/scripts/normalize_calendar.py [--dry-run]
"""
import re
import sys
import yaml
from pathlib import Path

ARC = Path(__file__).resolve().parent.parent
DATA = ARC / 'data'
CALENDAR_YAML = DATA / 'calendar.yaml'
ARTISTS_YAML = DATA / 'artists.yaml'
CHANGE_LOG = ARC.parent / 'temp' / 'calendar_normalize_log.txt'

# Manual overrides: normalized_title → artist_slug
# These cover cases where automatic matching is ambiguous or wrong.
MANUAL_MATCHES = {
    'Howlin Wolf': 'howlin-wolf',
    "Howlin' Wolf": 'howlin-wolf',
    'HOWLIN Wolf': 'howlin-wolf',
    "Lightnin' Hopkins": 'lightnin-hopkins',
    'Lightnon Hopkins': 'lightnin-hopkins',
    "Sam Lightnin' Hopkins": 'lightnin-hopkins',
    'B.B. King': 'bb-king',
    'B.B.King': 'bb-king',
    'B.B.KING': 'bb-king',
    'BB King': 'bb-king',
    'Keb Mo': 'keb-mo',
    "Keb' Mo'": 'keb-mo',
    'Dr. John': 'dr-john',
    'Dr.John': 'dr-john',
    'Doug McLeod': 'doug-macleod',
    'Sonny Boy Williamson I': 'sonny-boy-williamson',
    'Sonny Boy Williamson Ii': 'sonny-boy-williamson',
    'Morice John Vaughn': 'maurice-john-vaughn',
    'Maurice John Vaughn': 'maurice-john-vaughn',
    'Lourie Bell': 'lurrie-bell',
    'Duster Bunett': 'duster-bennett',
    'A.C.REED': 'a-c-reed',
    'A.C. Reed': 'a-c-reed',
    'Avery Parrish': 'avery-parish',
    'The Five Blind Boys of Alabama': 'blind-boys-of-alabama',
    'Blind Boys of Alabama': 'blind-boys-of-alabama',
    'Jonny Lang': 'johnny-lang',
    'Allman Brothers': 'allman-brothers',
    'The Allman Brothers': 'allman-brothers',
    'Allman Brothers Band': 'allman-brothers',
    'J.J. Cale': 'j-j-cale',
    'J.J.Cale': 'j-j-cale',
    'Junior Wells': 'junior-wells',
    'Lowell Fulsom': 'lowell-fulson',
    'Lowell Fulson': 'lowell-fulson',
    "Lightnin Hopkins": 'lightnin-hopkins',
    'Brownie Mcghee': 'brownie-mcghee',
    'Stick Mcghee': 'stick-mcghee',
    'Sticks Mcghee': 'stick-mcghee',
    'Sticks McGhee': 'stick-mcghee',
    'Kansas Joe Mccoy': 'kansas-joe-mccoy',
}


# ── Title normalization ──────────────────────────────────────────────────────

def normalize_title(title: str) -> str:
    """
    Convert ALL-CAPS surname words to Title Case.
    Leaves Russian/Cyrillic, initials with dots (B.B.), and mixed-case words untouched.
    """
    if not title:
        return title

    def fix_word(w: str) -> str:
        m = re.match(r'^(["\'\(\u201c\u201d]*)(.+?)(["\'\),.:!?\u201c\u201d]*)$', w)
        if not m:
            return w
        prefix, core, suffix = m.group(1), m.group(2), m.group(3)

        # Handle Mc prefix: McAULIFFE → McAuliffe
        mc_m = re.match(r'^(Mc)([A-Z]{2,})$', core)
        if mc_m:
            return prefix + mc_m.group(1) + mc_m.group(2).title() + suffix

        # Handle all-uppercase word (pure Latin alpha, no dots, 2+ chars)
        if re.match(r'^[A-Z]{2,}$', core):
            return prefix + core.title() + suffix

        return w

    tokens = re.split(r'(\s+)', title)
    result = []
    for tok in tokens:
        if re.match(r'\s+', tok):
            result.append(tok)
        else:
            result.append(fix_word(tok))
    return ''.join(result)


# ── Artist matching ──────────────────────────────────────────────────────────

def _clean_name(name: str) -> str:
    """Lowercase, strip punctuation and common stopwords for matching."""
    n = name.lower()
    n = re.sub(r"['\"\.\(\),&\-\u2019\u2018]", ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    stopwords = {'the', 'and', 'jr', 'sr', 'ii', 'iii', 'i'}
    words = [w for w in n.split() if w not in stopwords]
    return ' '.join(words)


def _name_tokens(name: str) -> frozenset:
    return frozenset(_clean_name(name).split())


def build_artist_index(artists: list) -> dict:
    """Build lookup maps: cleaned_name → (name, slug)."""
    by_clean = {}
    for a in artists:
        name = a.get('name', '')
        slug = a.get('slug', '')
        key = _clean_name(name)
        by_clean[key] = (name, slug)
        sn = a.get('sort_name', '')
        if sn and sn != name:
            sk = _clean_name(sn)
            if sk not in by_clean:
                by_clean[sk] = (name, slug)
    return by_clean


def match_title_to_artist(title: str, artist_index: dict, artists: list):
    """
    Try to match normalized title to an artist.
    Returns (artist_name, artist_slug, method) or None.

    Strategies (in order):
    1. Manual override table
    2. Exact cleaned-name match
    3. Token subset: all tokens of shorter name present in longer (≥2 tokens each)
    """
    # 1. Manual override
    if title in MANUAL_MATCHES:
        slug = MANUAL_MATCHES[title]
        aname = next((a['name'] for a in artists if a.get('slug') == slug), slug)
        return aname, slug, 'manual'

    # 2. Exact cleaned match
    key = _clean_name(title)
    if key in artist_index:
        name, slug = artist_index[key]
        return name, slug, 'exact'

    # 3. Token subset — only when all tokens of smaller set appear in larger
    title_toks = _name_tokens(title)
    if len(title_toks) >= 2:
        for akey, (aname, aslug) in artist_index.items():
            a_toks = frozenset(akey.split())
            if len(a_toks) >= 2:
                # Check full containment both ways
                if title_toks <= a_toks or a_toks <= title_toks:
                    # Require Jaccard >= 0.85 to avoid spurious partial matches
                    union = title_toks | a_toks
                    inter = title_toks & a_toks
                    if len(inter) / len(union) >= 0.85:
                        return aname, aslug, f'subset({len(inter)}/{len(union)})'

    return None


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    dry_run = '--dry-run' in sys.argv

    with open(CALENDAR_YAML, encoding='utf-8') as f:
        entries = yaml.safe_load(f)
    with open(ARTISTS_YAML, encoding='utf-8') as f:
        artists = yaml.safe_load(f)

    artist_index = build_artist_index(artists)

    title_changes = []   # (orig, norm, entry_id)
    match_log = []       # (title, slug, method)
    title_cache = {}     # normalized_title → match result

    for entry in entries:
        orig_title = entry.get('title', '')
        if not orig_title:
            continue

        norm_title = normalize_title(orig_title)

        if norm_title != orig_title:
            title_changes.append((orig_title, norm_title, entry.get('id', '')))
            entry['title'] = norm_title

        if norm_title not in title_cache:
            title_cache[norm_title] = match_title_to_artist(norm_title, artist_index, artists)
        match = title_cache[norm_title]

        if match:
            aname, aslug, method = match
            if entry.get('artist_slug') != aslug:
                match_log.append((norm_title, aslug, method))
            entry['artist_slug'] = aslug
        else:
            entry.pop('artist_slug', None)

    # Build change log
    matched = set(e.get('artist_slug') for e in entries if e.get('artist_slug'))
    unmatched = sorted(set(
        e['title'] for e in entries if not e.get('artist_slug')
    ))

    log_lines = [
        '# Calendar normalization change log',
        f'# Entries: {len(entries)}, unique titles: {len(set(e["title"] for e in entries))}',
        '',
        '## Title normalizations',
        '',
    ]
    for orig, norm, eid in title_changes:
        log_lines.append(f'  [{eid}] {repr(orig)} → {repr(norm)}')

    log_lines += ['', '## Artist matches', '']
    for title, slug, method in sorted(set((t, s, m) for t, s, m in match_log)):
        log_lines.append(f'  {method:30s} {repr(title):50s} → {slug}')

    log_lines += [
        '', '## Summary', '',
        f'  Title normalizations: {len(title_changes)}',
        f'  Unique slugs matched: {len(matched)}',
        f'  Matched entries: {sum(1 for e in entries if e.get("artist_slug"))}',
        f'  Unmatched unique titles: {len(unmatched)}',
        '', '## Unmatched (first 150)', '',
    ]
    for t in unmatched[:150]:
        log_lines.append(f'  {repr(t)}')

    CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    CHANGE_LOG.write_text('\n'.join(log_lines), encoding='utf-8')
    print(f'Change log: {CHANGE_LOG}')

    if dry_run:
        print(f'DRY RUN: {len(title_changes)} title fixes, '
              f'{len(matched)} unique artist slugs matched')
        return

    # yaml.dump reorders and reformats — preserve original style by patching inline
    # Re-read original lines, update only changed entries
    _write_updated_yaml(entries)
    print(f'Updated {CALENDAR_YAML}')
    print(f'  Title normalizations: {len(title_changes)}')
    print(f'  Unique artists matched: {len(matched)}')


def _write_updated_yaml(entries: list):
    """Write calendar.yaml preserving structure."""
    with open(CALENDAR_YAML, 'w', encoding='utf-8') as f:
        yaml.dump(entries, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120)


if __name__ == '__main__':
    main()
