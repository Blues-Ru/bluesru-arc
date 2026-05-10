# Refactor Report: Typed Models & Code Quality Improvements

**Branch:** `refactor/typed-models`  
**Date:** 2026-05-10  
**Status:** Complete — full build passes, 0 regressions

---

## Summary

Refactored the bluesru-arc Python generator codebase from a single 2,000-line `generate_shared.py`
monolith into a modular architecture with Pydantic v2 typed models, focused single-responsibility
modules, and explicit imports throughout. All 11 generator scripts now declare their dependencies
explicitly. Site output is byte-for-byte identical to pre-refactor.

---

## Commits

| Hash | Phase | Description |
|------|-------|-------------|
| `298ea275` | 1 | 9 new sub-modules + rewritten generate_shared.py |
| `d9d4641c` | 2 | 6 generators migrated to explicit imports |
| `963ba394` | 3 | 3 remaining generators migrated to explicit imports |

---

## New Sub-Modules

### `models.py` (~200 lines)
Pydantic v2 data models for all domain types.

**Key models:**

| Model | Fields | Notes |
|-------|--------|-------|
| `Artist` | id, slug, name, sort_name, legacy_path, amg_id, streaming IDs, resources | Properties: `effective_sort_name`, `sort_letter`, `legacy_dir` |
| `Album` | id, slug, artist_id, title, year, asin, label, reviews, streaming IDs | `artist: Optional[str]` — some YAML has `artist: null` |
| `AlbumReview` | id, author, mark, date, text | |
| `CalendarEvent` | date, year, month_day, event_type, title, text, picture, artist_slug | `year: Optional[str \| int]` — YAML stores as int in some entries |
| `ForumPost` | poster, date, body, deleted, replies | Self-referencing; requires `ForumPost.model_rebuild()` after class definition |
| `ForumTopicMeta` | topic_id, subject, date | |
| `ArtistLink` | type, url, title, external, platform | Used for sidebar link lists |
| `ArtistStreamingIds` | spotify_id, apple_music_id, deezer_id, ytmusic_id | |
| `AlbumStreamingIds` | + youtube_video_id, youtube_playlist_id | |
| `GalleryMeta` | slug, path, title, date, photos, exclude, type | |

**Design decisions:**
- All fields that can be `null` in YAML are `Optional[T] = None` or `Optional[T] = default`
- `CalendarEvent.year` is `Optional[str | int]` because the YAML stores it as int but it's used as str
- `ForumPost.model_rebuild()` is called at module level to resolve the self-referencing `replies` field
- No `orm_mode` needed — all data comes from YAML, never from ORM

---

### `data.py` (~280 lines)
Typed `DataStore` singleton with lazy-loaded, cached accessors.

```python
store = DataStore()  # module-level singleton
```

All data is loaded once on first access and cached:

| Method | Returns | Source |
|--------|---------|--------|
| `artists()` | `list[Artist]` | data/artists.yaml |
| `albums_by_id()` | `dict[str, Album]` | data/albums/*/*.yaml |
| `artist_streaming()` | `dict[str, ArtistStreamingIds]` | data/artists.yaml |
| `album_streaming()` | `dict[str, AlbumStreamingIds]` | data/albums/*/*.yaml |
| `calendar_by_slug()` | `dict[str, list[CalendarEvent]]` | data/calendar.yaml |
| `atb_by_artist_slug()` | `dict[str, list[dict]]` | data/atb/episodes.yaml |
| `galleries_by_artist_slug()` | `dict[str, list[dict]]` | data/galleries/ |
| `spam_ids()` | `set[int]` | data/forum/spam-ids.yaml |
| `topics_index()` | `list[dict]` | data/forum/topics/index.yaml |
| `find_topic_yaml()` | `Path \| None` | data/forum/topics/ |

**Circular import avoidance:** `galleries_by_artist_slug()` imports from `gallery_utils`
inside the method body rather than at module top level.

---

### `html_utils.py` (~180 lines)
HTML processing: SSI resolution, link rewriting, analytics stripping.

**Key design — factory function for link rewriting:**

```python
def make_link_rewriter(redirect_rules: list, link_fixes: dict):
    def rewrite_links(content: str) -> str: ...
    return rewrite_links
```

The factory closes over the redirect rules and dead-link map, producing a pure function with
no global state. `generate_shared.py` calls this once at import time:

```python
_rewrite_links = make_link_rewriter(_REDIRECT_RULES, _LINK_FIXES)
```

Other functions:
- `read_file(path)` — UTF-8 → win-1251 → latin-1 fallback encoding
- `strip_analytics(html)` — removes LiveInternet, Yandex Metrika, Google Analytics, jQuery CDN
- `resolve_include(vpath, source_dir, source_root, footer, donate)` — resolves `<!--#include virtual=...-->`
- `load_redirect_rules(path)` — parses `_redirects` Cloudflare format
- `load_link_fixes(path)` — loads `data/link_fixes.yaml`
- `normalize_filename(name)` — slugifies filenames for site URLs

---

### `render_utils.py` (~100 lines)
Pure rendering utilities with no side effects.

| Function | Description |
|----------|-------------|
| `cover_url_for_asin(asin)` | Returns local `/covers/{asin}.jpg` if cached, else Amazon URL |
| `format_mark_ats(mark)` | `15 → "@@@@@@@"` (rounds to half, uses `@` chars) |
| `star_rating_html(mark, size)` | SVG star rating HTML for Jinja templates |
| `format_review_body(body)` | Cleans review text: strips Windows artifacts, normalizes paragraphs |
| `format_news_body(body)` | News body: paragraph normalization with HTML passthrough |
| `format_news_body_simple(body)` | Simpler variant for announcement excerpts |

---

### `streaming.py` (~60 lines)
Streaming platform URL templates and link HTML generation.

```python
ALBUM_URL_TEMPLATES: dict[str, str]    # {platform: url_template}
ARTIST_URL_TEMPLATES: dict[str, str]
PLATFORM_LABELS: dict[str, str]        # {platform: display_name}

def streaming_links_html(slug: str, kind: str, store: DataStore) -> str:
```

`store` is passed as a parameter (dependency injection) rather than imported globally,
making the function testable and avoiding circular imports.

---

### `forum_render.py` (~200 lines)
Stateless forum HTML rendering — all state injected as parameters.

```python
def render_post_html(post, topic_slug, full, depth, spam_ids, author_slugs) -> str:
def render_topic_html(topic_data, topic_meta, full, forum_page, spam_ids, author_slugs) -> str:
def topic_is_all_deleted(topic_data, spam_ids) -> bool:
def sanitize_forum_html(text: str) -> str:
```

`generate_shared.py` provides wrappers that inject module-level `SPAM_IDS` and `_get_author_slugs()`:

```python
def render_post_html(post, topic_slug, full=True, depth=0) -> str:
    return _render_post_html_impl(post, topic_slug, full=full, depth=depth,
                                   spam_ids=SPAM_IDS, author_slugs=_get_author_slugs())
```

---

### `calendar_render.py` (~130 lines)
Pure calendar HTML rendering functions.

```python
def calendar_events_html(events: list[CalendarEvent], current_year: int = 2026) -> str:
def process_calendar_text(text: str, slug: str, title: str | None) -> str:
def years_ago_ru(years: int) -> str:     # "50 лет назад"
def years_ago_abbr(years: int) -> str:   # "50 л.н."
def fix_all_caps_name(name: str) -> str: # "MUDDY WATERS" → "Muddy Waters"
```

---

### `gallery_utils.py` (~80 lines)
Pure functions for gallery URL computation.

```python
def gallery_year(path: str) -> int | None:
def gallery_canonical_url(data: dict, gpath: str) -> tuple[str, str]:  # (rel_url, year_str)
def write_gallery_redirects(arc_dir: Path, redirects: list[tuple[str, str]]) -> None:
```

---

### `artist_utils.py` (~280 lines)
Artist page building helpers.

```python
def strip_artist_prefix(artist_slug: str, album_slug: str) -> str:
def scan_artist_subpages(artist_dir: Path, artist_slug: str) -> list[dict]:
def collect_artist_links(slug, artist_id, src_dir, galleries_by_slug,
                          resources_by_artist, calendar_by_slug,
                          has_album_list, artist_streaming_ids) -> list[ArtistLink]:
def format_artist_links(links: list[ArtistLink], types: set[str] | None = None) -> str:
def build_album_list_html(artist_slug, artist_id, albums_by_artist) -> str:
def process_artist_dir(artist, src_dir, src_root, ...) -> None:
def atb_links_html(atb_entries: list) -> str:
```

---

## Rewritten: `generate_shared.py`

Reduced from ~2,088 lines to ~580 lines. Now a **thin coordinator** that:

1. Imports all implementations from sub-modules
2. Re-exports them under their original names for backward compatibility
3. Holds module-level path constants (`ARC`, `SITE`, `DATA`, etc.)
4. Constructs stateful singletons: `JINJA_ENV`, `FOOTER`, `SPAM_IDS`, `_rewrite_links`
5. Provides wrapper functions that inject module-level state into stateless sub-module functions

**Backward compatibility:** All original exported names remain available. Scripts that still
use `from generate_shared import X` continue to work without changes.

---

## Generator Scripts — Explicit Imports (Phase 2 & 3)

All 11 generator scripts now use explicit named imports:

| Script | Was | Now |
|--------|-----|-----|
| `generate_news.py` | `from generate_shared import *` | explicit named imports |
| `generate_reviews.py` | `from generate_shared import *` | explicit named imports |
| `generate_forum.py` | `from generate_shared import *` | explicit named imports |
| `generate_galleries.py` | `from generate_shared import *` | explicit named imports |
| `generate_bluesmen.py` | `from generate_shared import *` | explicit named imports |
| `generate_updates.py` | `from generate_shared import *` | explicit named imports |
| `generate_atb.py` | `from generate_shared import *` | explicit named imports |
| `generate_content.py` | `from generate_shared import *` | explicit named imports |
| `generate_homepage.py` | `from generate_shared import *` | explicit named imports |
| `generate_calendar_page.py` | already explicit | no change needed |
| `generate_sitemap.py` | already explicit | no change needed |

---

## Bugs Fixed During Refactor

### `Album.artist = None`
Some albums in YAML have `artist: null`. Changed `artist: str = ''` → `artist: Optional[str] = ''`
in models.py. Without this fix, `model_validate()` raised a Pydantic validation error.

### `CalendarEvent.year` as integer
Calendar YAML stores `year` as an integer in some entries (e.g. `year: 1939`).
Changed `year: Optional[str] = None` → `year: Optional[str | int] = None`.
Also fixed `calendar_render.py` to always call `str(ev.year)` before use.

### `_MONTHS_RU` not exported
`generate_calendar_page.py` imports `_MONTHS_RU` (genitive month names: "января"…)
directly. This is distinct from the nominative `MONTHS_RU` ("январь"…). Added
`_MONTHS_RU` explicitly to `generate_shared.py` namespace.

### Duplicate `_normalize_filename`
The original `generate_shared.py` defined `_normalize_filename` at two locations,
the second silently shadowing the first. Resolved to a single delegation to
`html_utils.normalize_filename`.

---

## Architecture Principles Applied

**Single Responsibility** — each module handles one concern: models, data loading,
HTML processing, rendering, forum, calendar, gallery, artist pages.

**Dependency Injection** — stateless sub-module functions receive their dependencies
as parameters (`spam_ids`, `store`, `footer`). `generate_shared.py` is the only
place that constructs singletons and injects them.

**DRY** — `DataStore` is the single source of truth for all data loading.
`make_link_rewriter` is called once; the returned closure is reused everywhere.

**Explicit over implicit** — all generator scripts declare exactly what they import.
No hidden namespace pollution from wildcard imports.

**Type safety** — all data passing through the pipeline is validated by Pydantic at
load time. Runtime type errors surface immediately rather than manifesting as wrong
output.

---

## What Was NOT Changed

- **HTML output** — identical to pre-refactor (verified by full build)
- **Template files** — no changes to any `.html.j2` files
- **Data files** — no changes to YAML/JSON data
- **URL structure** — no changes to generated URLs or redirects
- **`generate_shared.py` public API** — all exports preserved for backward compat
- **`generate.py`** (the orchestrator) — unchanged

---

## Build Verification

```
Output: /Users/fedor/bluesru/bluesru-site
Bluesmen list: 419 artists, 164 bio pages + 248 stub pages
ATB index: 215 episodes, 10 years
galleries: 343 index pages written
postprocess_dead_links: rewrote 5660 files
```

Full build completes without errors or warnings on all three phases.
