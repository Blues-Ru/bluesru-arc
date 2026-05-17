#!/usr/bin/env python3
"""One-shot: register artists currently lumped under /artist/various-musicians/.

For each new artist row:
  - allocate next-available id (or reuse existing one if slug already in artists.yaml)
  - find all albums whose `artist` text matches any of the configured matchers
  - set album.artist_id
  - if album.artist text differs from canonical (collab album), rewrite slug to
    `{artist-slug}-{slugify(title)}` so the URL prefix strip yields just the title
  - move YAML file to data/albums/{artist-slug}/{slug}.yaml
  - record the old `/artist/various-musicians/{old-slug}/` → new-URL redirect

Output:
  - updated data/artists.yaml (appended rows)
  - moved/edited data/albums/*/*.yaml files
  - data/album-migration-redirects.yaml (consumed by generate_redirects.py)
"""
import re
import sys
from pathlib import Path
import yaml

DATA = Path(__file__).resolve().parents[1] / 'data'

# (display_name, slug, sort_name)
BUCKET_A = [
    ('Animals', 'animals', 'Animals'),
    ('Big Twist & The Mellow Fellows', 'big-twist-the-mellow-fellows', 'Big Twist & The Mellow Fellows'),
    ('James Montgomery Band', 'james-montgomery-band', 'Montgomery, James (Band)'),
    ('Jimmy Johnson', 'jimmy-johnson', 'Johnson, Jimmy'),
    ('John Renbourn', 'john-renbourn', 'Renbourn, John'),
    ('Rufus Thomas', 'rufus-thomas', 'Thomas, Rufus'),
    ('Alvin Lee', 'alvin-lee', 'Lee, Alvin'),
    ('Archie Edwards', 'archie-edwards', 'Edwards, Archie'),
    ('Blues Pills', 'blues-pills', 'Blues Pills'),
    ('Bob Dylan', 'bob-dylan', 'Dylan, Bob'),
    ('Charlie Sayles', 'charlie-sayles', 'Sayles, Charlie'),
    ('Chubby Carrier and the Bayou Swamp Band', 'chubby-carrier', 'Carrier, Chubby'),
    ('David "Honeyboy" Edwards', 'honeyboy-edwards', 'Edwards, David "Honeyboy"'),
    ('David Wilcox', 'david-wilcox', 'Wilcox, David'),
    ('Dennis Gruenling', 'dennis-gruenling', 'Gruenling, Dennis'),
    ('George Smith', 'george-smith', 'Smith, George'),
    ('Groove Hogs', 'groove-hogs', 'Groove Hogs'),
    ('Harvey Mandel', 'harvey-mandel', 'Mandel, Harvey'),
    ('Henry Butler', 'henry-butler', 'Butler, Henry'),
    ('Hot Tuna', 'hot-tuna', 'Hot Tuna'),
    ('Indigenous', 'indigenous', 'Indigenous'),
    ('J. Geils Band', 'j-geils-band', 'Geils, J. (Band)'),
    ('Jody Williams', 'jody-williams', 'Williams, Jody'),
    ('John Jackson', 'john-jackson', 'Jackson, John'),
    ('John Nemeth', 'john-nemeth', 'Nemeth, John'),
    ('Junior Kimbrough', 'junior-kimbrough', 'Kimbrough, Junior'),
    ('Kenny Blue Ray', 'kenny-blue-ray', 'Ray, Kenny Blue'),
    ('Lonnie Johnson', 'lonnie-johnson', 'Johnson, Lonnie'),
    ('Luther Tucker', 'luther-tucker', 'Tucker, Luther'),
    ('Mississippi John Hurt', 'mississippi-john-hurt', 'Hurt, Mississippi John'),
    ('Paul Oscher', 'paul-oscher', 'Oscher, Paul'),
    ('Robert Lucas', 'robert-lucas', 'Lucas, Robert'),
    ('Roy Rogers', 'roy-rogers', 'Rogers, Roy'),
    ('Steve Miller Band', 'steve-miller-band', 'Miller, Steve (Band)'),
    ('Sugar Blue', 'sugar-blue', 'Sugar Blue'),
    ('T-Model Ford', 't-model-ford', 'Ford, T-Model'),
    ('Terrell', 'terrell', 'Terrell'),
    ('Tony Joe White', 'tony-joe-white', 'White, Tony Joe'),
]

BUCKET_B = [
    ('Ben Harper', 'ben-harper', 'Harper, Ben'),
    ('Double Trouble', 'double-trouble', 'Double Trouble'),
    ('Robert Palmer', 'robert-palmer', 'Palmer, Robert'),
    ('Rusty Zinn', 'rusty-zinn', 'Zinn, Rusty'),
    ('Tony Bennett', 'tony-bennett', 'Bennett, Tony'),
]

BUCKET_C = [
    ('Aaron Neville', 'aaron-neville', 'Neville, Aaron'),
    ('Amos Milburn', 'amos-milburn', 'Milburn, Amos'),
    ('Big Jay McNeely', 'big-jay-mcneely', 'McNeely, Big Jay'),
    ('Big Maceo', 'big-maceo', 'Big Maceo'),
    ('Big Maybelle', 'big-maybelle', 'Big Maybelle'),
    ('Blind Willie McTell', 'blind-willie-mctell', 'McTell, Blind Willie'),
    ('Charles Brown', 'charles-brown', 'Brown, Charles'),
    ('Charley Patton', 'charley-patton', 'Patton, Charley'),
    ('Eddie Cusic', 'eddie-cusic', 'Cusic, Eddie'),
    ('Eddie "One String" Jones', 'eddie-one-string-jones', 'Jones, Eddie "One String"'),
    ('Gus Cannon', 'gus-cannon', 'Cannon, Gus'),
    ('Sleepy John Estes', 'sleepy-john-estes', 'Estes, Sleepy John'),
    ('J.D. Short', 'j-d-short', 'Short, J.D.'),
    ('Joe Callicott', 'joe-callicott', 'Callicott, Joe'),
    ('Joe Hill Louis', 'joe-hill-louis', 'Louis, Joe Hill'),
    ("Lightnin' Slim", 'lightnin-slim', "Lightnin' Slim"),
    ('Little Willie Littlefield', 'little-willie-littlefield', 'Littlefield, Little Willie'),
    ('Magic Sam', 'magic-sam', 'Magic Sam'),
    ('Mississippi Sheiks', 'mississippi-sheiks', 'Mississippi Sheiks'),
    ('Otha Turner', 'otha-turner', 'Turner, Otha'),
    ('Peg Leg Sam', 'peg-leg-sam', 'Peg Leg Sam'),
    ('Percy Mayfield', 'percy-mayfield', 'Mayfield, Percy'),
    ('Pink Anderson', 'pink-anderson', 'Anderson, Pink'),
    ('Robert Lockwood Jr.', 'robert-lockwood-jr', 'Lockwood, Robert (Jr.)'),
    ('Robert Pete Williams', 'robert-pete-williams', 'Williams, Robert Pete'),
    ('Robert Wilkins', 'robert-wilkins', 'Wilkins, Robert'),
    ('Roosevelt Sykes', 'roosevelt-sykes', 'Sykes, Roosevelt'),
    ('Slim Harpo', 'slim-harpo', 'Slim Harpo'),
    ('St. Louis Jimmy', 'st-louis-jimmy', 'St. Louis Jimmy'),
    ('Tommy Ridgley', 'tommy-ridgley', 'Ridgley, Tommy'),
    ('Willie Mabon', 'willie-mabon', 'Mabon, Willie'),
    ('Hadda Brooks', 'hadda-brooks', 'Brooks, Hadda'),
    ('Katie Webster', 'katie-webster', 'Webster, Katie'),
    ('Professor Longhair', 'professor-longhair', 'Professor Longhair'),
    ('Dirty Dozen Brass Band', 'dirty-dozen-brass-band', 'Dirty Dozen Brass Band'),
    ('Monk Boudreaux', 'monk-boudreaux', 'Boudreaux, Monk'),
    ('Buster Benton', 'buster-benton', 'Benton, Buster'),
    ('Carl Weathersby', 'carl-weathersby', 'Weathersby, Carl'),
    ('Fenton Robinson', 'fenton-robinson', 'Robinson, Fenton'),
    ('Hound Dog Taylor', 'hound-dog-taylor', 'Taylor, Hound Dog'),
    ('Jerry "Boogie" McCain', 'jerry-mccain', 'McCain, Jerry "Boogie"'),
    ('Jimmy McCracklin', 'jimmy-mccracklin', 'McCracklin, Jimmy'),
    ('Joanna Connor', 'joanna-connor', 'Connor, Joanna'),
    ('Mojo Buford', 'mojo-buford', 'Buford, Mojo'),
    ('Syl Johnson', 'syl-johnson', 'Johnson, Syl'),
    ('Mahalia Jackson', 'mahalia-jackson', 'Jackson, Mahalia'),
    ('Mose Allison', 'mose-allison', 'Allison, Mose'),
    ('Odetta', 'odetta', 'Odetta'),
    ('Jimmy Rushing', 'jimmy-rushing', 'Rushing, Jimmy'),
    ('Jimmy Smith', 'jimmy-smith', 'Smith, Jimmy'),
    ('Dee Dee Bridgewater', 'dee-dee-bridgewater', 'Bridgewater, Dee Dee'),
    ('Charlie Rich', 'charlie-rich', 'Rich, Charlie'),
    ('Spider John Koerner', 'spider-john-koerner', 'Koerner, Spider John'),
    ('Chris Thomas King', 'chris-thomas-king', 'King, Chris Thomas'),
    ('Hank Shizzoe', 'hank-shizzoe', 'Shizzoe, Hank'),
    ('Ian Siegal', 'ian-siegal', 'Siegal, Ian'),
    ('John Lee Hooker Jr.', 'john-lee-hooker-jr', 'Hooker, John Lee (Jr.)'),
    ('Jonny Lang', 'jonny-lang', 'Lang, Jonny'),
    ('Robert Cray', 'robert-cray', 'Cray, Robert'),       # already exists (id 19)
    ('Robert Randolph', 'robert-randolph', 'Randolph, Robert'),
    ('Super Chikan', 'super-chikan', 'Super Chikan'),
    ('Susan Tedeschi', 'susan-tedeschi', 'Tedeschi, Susan'),
    ('Paul Rodgers', 'paul-rodgers', 'Rodgers, Paul'),
    ('Mick Fleetwood Blues Band', 'mick-fleetwood-blues-band', 'Fleetwood, Mick (Blues Band)'),
]

# Extra album-text matchers beyond exact name match (collab/extended-band cases).
EXTRA_MATCHERS = {
    'roy-rogers':            {'roy rogers & norton buffalo'},
    'lonnie-johnson':        {'lonnie johnson with elmer snowden'},
    'sleepy-john-estes':     {'hammie nixon & sleepy john estes'},
    'spider-john-koerner':   {'ray & glover, koerner'},
    'ben-harper':            {'ben harper & the blind boys of alabama'},
    'robert-cray':           {'the robert cray band'},
    'robert-randolph':       {'robert randolph & the family band'},
    'otha-turner':           {'otha turner and the rising star fife & drum band'},
    'hound-dog-taylor':      {'hound dog taylor & the houserockers'},
    'jonny-lang':            {'jonny lang & the big bang'},
}

ALL_REGISTRATIONS = BUCKET_A + BUCKET_B + BUCKET_C


def slugify_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:55]


def main() -> None:
    artists_yaml = DATA / 'artists.yaml'
    artists = yaml.safe_load(artists_yaml.read_text(encoding='utf-8')) or []
    by_slug = {a['slug']: a for a in artists}
    next_id = max(int(a['id']) for a in artists) + 1

    # Build name → artist_id map after additions
    artists_added = 0
    for name, slug, sort_name in ALL_REGISTRATIONS:
        if slug in by_slug:
            continue
        artists.append({
            'id': next_id,
            'slug': slug,
            'name': name,
            'sort_name': sort_name,
            'legacy_path': f'/artist/{slug}/',
            'resources': [],
        })
        by_slug[slug] = artists[-1]
        next_id += 1
        artists_added += 1

    # Resolve slug → id for the registrations we’re processing
    artist_id_by_slug = {a['slug']: a['id'] for a in artists}

    # Load all album files ONCE
    album_dir = DATA / 'albums'
    print("Loading album YAMLs…")
    album_data: list[tuple[Path, dict]] = []
    for yf in album_dir.rglob('*.yaml'):
        d = yaml.safe_load(yf.read_text(encoding='utf-8')) or {}
        album_data.append((yf, d))
    print(f"  {len(album_data)} albums loaded")

    # Build artist-text → registration mapping (for one-pass linkage)
    text_to_reg: dict[str, tuple[str, str, str]] = {}  # text(lower) → (name, slug, sort_name)
    for entry in ALL_REGISTRATIONS:
        name, slug, sort_name = entry
        text_to_reg[name.lower()] = entry
        for m in EXTRA_MATCHERS.get(slug, set()):
            text_to_reg[m] = entry

    redirects: list[tuple[str, str]] = []
    moves = linked = renamed = 0

    for old_yf, d in album_data:
        if d.get('artist_id'):
            continue
        a_text = (d.get('artist') or '').strip().lower()
        entry = text_to_reg.get(a_text)
        if not entry:
            continue
        name, slug, _ = entry
        aid = artist_id_by_slug[slug]

        old_slug = d.get('slug') or ''
        title = d.get('title') or ''
        d['artist_id'] = aid
        d['artist_slug'] = slug

        is_collab = a_text != name.lower()
        new_slug = old_slug
        if is_collab or not old_slug.startswith(slug + '-'):
            new_slug = f'{slug}-{slugify_title(title)}' if title else f'{slug}-untitled'
            d['slug'] = new_slug
            renamed += 1

        target_dir = album_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target_yf = target_dir / f'{new_slug}.yaml'

        target_yf.write_text(
            yaml.dump(d, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding='utf-8',
        )

        stripped = new_slug[len(slug) + 1:] if new_slug.startswith(slug + '-') else new_slug
        old_url = f'/artist/various-musicians/{old_slug}/'
        new_url = f'/artist/{slug}/{stripped}/'
        if old_url != new_url:
            redirects.append((old_url, new_url))

        if target_yf != old_yf:
            old_yf.unlink()
            try:
                old_yf.parent.rmdir()
            except OSError:
                pass
            moves += 1
        linked += 1

    # Write artists.yaml
    artists_yaml.write_text(
        yaml.dump(artists, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding='utf-8',
    )

    # Write migration redirects
    redirects_path = DATA / 'album-migration-redirects.yaml'
    # Dedupe and sort
    redirects = sorted(set(redirects))
    redirects_path.write_text(
        yaml.dump([{'from': f, 'to': t} for f, t in redirects],
                  allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding='utf-8',
    )

    print(f"Done: {artists_added} new artist rows, {linked} albums linked, "
          f"{moves} files moved, {renamed} slugs renamed, "
          f"{len(redirects)} redirects written to album-migration-redirects.yaml")


if __name__ == '__main__':
    main()
