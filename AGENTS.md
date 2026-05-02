# AGENTS.md — Blues.Ru Archive: Agent Reference

Quick orientation for AI agents working in this repository.
Full project spec: `../CLAUDE.md` (kept for historical context — prefer this file for current structure).

---

## Repository Overview

`bluesru-arc/` is a self-contained static site generator. It reads structured YAML data and legacy HTML content, produces a fully static site in `../bluesru-site/`, deployed to Cloudflare Pages.

**No database. No runtime server. Everything is pre-generated.**

```
bluesru-arc/          ← this repo (committed)
bluesru-site/         ← generated output (NOT committed, beside this repo)
bluesru-media/        ← large media: photos + MP3s (NOT committed, local + R2)
bluesru-media.cache/  ← thumbnails (-400w.jpg) (NOT committed, local + R2)
```

---

## Build System — Use `make`

**Always use `make` targets, not raw script calls.** The Makefile sets `BLUESRU_ROOT` and other env vars correctly.

### Full Builds

```bash
make build              # sequential, safe, ~5-10 min
make -j16 build-parallel  # DAG-based parallel, ~2-3 min
make backup             # rename existing bluesru-site/ with timestamp (runs automatically in build)
```

### Individual Sections (fast iteration)

```bash
make content     # static legacy HTML (bluesnews, beefheart, ethnotrip, zappazuhoi, band, efes…)
make bluesmen    # artist pages (422 artists → /artist/{slug}/)
make reviews     # album review pages (1652 albums → /artist/{a-slug}/{alb-slug}/)
make news        # news archive (1082 stories → /news/YYYY/MM/DD/storyN/)
make updates     # site announcements (968 items → /updates/YYYY/)
make atb         # radio show pages (349 episodes → /atb/{slug}/)
make galleries   # photo gallery pages (295 galleries → /photo/YYYY/{slug}/)
make photo       # photo gallery index page
make forum       # all forum pages (5230 topics); slow — use shards for speed
make forum-index # forum index pages only (fast)
make forum-plan  # split topics into 8 shard files (prerequisite for forum-shard-*)
make forum-shard-0  # generate topics from one shard (run 0–7 in parallel)
make homepage    # index.html + /links/ directory
make calendar    # /calendar/ pages (2880 events)
make data        # pre-built JSON files (/data/calendar.json, artist albums)
make anagrams    # /anagrams/ page
make postprocess # rewrite dead links in ALL generated HTML — run after any HTML change
make deploy      # copy _redirects, _headers, robots.txt to bluesru-site/
```

### Development

```bash
make serve       # start local test server at http://localhost/ (or http://a.blues.ru/)
make thumbs      # generate 400px thumbnails for gallery photos (macOS only, uses sips)
make thumbs-dry  # preview what thumbs would be generated
make deps        # pip install -r requirements.txt (auto-runs before build)
```

### Deployment

```bash
make push           # git push to GitHub (triggers CF Pages build)
make push-media     # rclone sync bluesru-media/ → r2:bluesru-media/bluesru-media/
make push-cache     # rclone sync bluesru-media.cache/ → r2:bluesru-media/bluesru-media.cache/
make push-all       # push-media + push-cache + push
```

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `BLUESRU_ROOT` | `../` (parent of repo) | Workspace root (set by Makefile; Makefile has it hardcoded — update for non-standard layouts) |
| `BLUESRU_SITE` | `../bluesru-site` | Output directory |
| `CF_PAGES=1` | (unset locally) | Set by CF Pages; moves site output inside repo |

---

## Repository Layout

```
bluesru-arc/
├── scripts/               Python generators and dev tools
│   ├── generate_shared.py   Shared constants, helpers, data loaders (all generators import this)
│   ├── generate.py          Section dispatcher (--section NAME)
│   ├── generate_bluesmen.py Artist pages
│   ├── generate_reviews.py  Album review pages
│   ├── generate_news.py     News archive
│   ├── generate_updates.py  Site announcements
│   ├── generate_forum.py    Forum pages + sharding support
│   ├── generate_galleries.py Photo gallery pages + index
│   ├── generate_atb.py      Radio show pages
│   ├── generate_content.py  Static content copy + processing
│   ├── generate_homepage.py Homepage + links directory
│   ├── generate_calendar_page.py Calendar pages
│   ├── generate_data_json.py Pre-built JSON for client-side JS
│   ├── generate_anagrams.py Anagrams game page
│   ├── forum_plan.py        Split forum topics into shards
│   ├── serve.py             Local test server
│   └── thumbs.py            Thumbnail generator
│
├── templates/             Jinja2 templates (.j2) — one per page type
├── includes/              HTML fragments: footer.inc, donate.inc
├── css/                   Site CSS (→ deployed at /css/)
├── js/                    Site JS (→ deployed at /js/)
├── covers/                Amazon cover cache ({asin}.jpg, ~1885 files, → /covers/)
├── images/                Site-wide images (→ /images/)
├── forum/                 Forum static assets: liveforum.css, liveforum.js
├── news/images/           News inline images (→ /news/images/)
├── content/               1,250+ legacy HTML files mirroring site URL tree
├── data/                  ~7,600 YAML files — ALL site content lives here
├── calendar/images/       1,504 calendar event images (MMDD-Name.jpg, → /calendar/images/)
│
├── tools/                 Utility scripts for data enrichment (not part of build)
│   ├── streaming/           Music service API integration
│   ├── enrichment/          LLM-based data enrichment
│   ├── audio/               ATB transcription pipeline
│   ├── spam/                Forum spam detection
│   ├── gallery/             Gallery data tools
│   └── validate/            Link auditing
│
├── Makefile               Build orchestration (USE THIS, not raw scripts)
├── _redirects             Cloudflare Pages redirect rules (478 lines)
├── _headers               CF Pages cache/content-type headers
├── wrangler.toml          Cloudflare Pages config
├── requirements.txt       Python deps: jinja2, pyyaml
└── functions/
    └── _middleware.js     CF Pages Worker: proxies /bluesru-media/* → R2
```

---

## Data Architecture

**All content lives in `data/`.** Generators read YAML, write HTML. No SQL, no database.

```
data/
├── artists.yaml          422 artists: id, slug, name, sort_name, streaming IDs, resources[]
├── albums/               ~2,067 YAML files: data/albums/{artist-slug}/{artist-slug-album-slug}.yaml
│   └── {artist}/           each file: id, slug, artist_id, title, year, label, asin,
│                           apple_music_id, spotify_id, deezer_id, ytmusic_id, reviews[]
├── calendar.yaml         2,880 events indexed by MM-DD (2.1 MB)
├── news/                 1,082 stories as Markdown+YAML: data/news/YYYY/MM/DD/{slug}.md
├── updates/              968 announcements: data/updates/YYYY/{slug}.md
├── forum/
│   ├── topics/           5,230 forum topics: data/forum/topics/YYYY/MM/YYYY-MM-DD-topic-N.yaml
│   ├── topics-index.yaml Fast index for forum pagination
│   └── spam-ids.yaml     Post IDs to suppress
├── atb/
│   ├── episodes.yaml     349 radio episodes with summary, files[], transcript
│   └── transcripts/      Markdown with <a id="tN"> timecode anchors
├── galleries/
│   ├── index.yaml        Master gallery index (all 295 galleries)
│   └── {slug}.yaml       Per-gallery metadata + photos[]
├── links.yaml            Blues site directory (149 URLs, 20 categories)
├── link_fixes.yaml       Dead internal links → redirect targets (applied by postprocess)
├── bluesmen-extra-redirects.yaml
└── bluesnews-redirects.yaml
```

### Key YAML Schemas

**Artist** (`data/artists.yaml` entry):
```yaml
id: 2
slug: luther-allison
name: Luther Allison
sort_name: Allison, Luther        # for alphabetical cross-reference
legacy_path: /bluesmen/Allison_Luther/
spotify_id: 7EynH3keqfKUmauyaeZoxv
apple_music_id: '86447'
resources:
  - type: article
    url: /artist/luther-allison/bio.htm
```

**Album** (`data/albums/luther-allison/luther-allison-live-and-well.yaml`):
```yaml
id: 123
slug: luther-allison-live-and-well
artist_id: 2
title: Live and Well
year: 1972
label: Motown
asin: B000002MXG
apple_music_id: '12345'
deezer_id: '67890'
reviews:
  - id: 5001
    author: John Doe
    mark: 9          # integer 0–20 → rendered as @ symbols (mark/2 full + mark%2 half)
    date: 2006-05-31
    text: <p>HTML body</p>
```

**News/Update** (Markdown+YAML frontmatter):
```markdown
---
id: 1001
date: 2024-05-02
title: New Album Released
slug: new-album-released
---
<p>HTML body</p>
```

---

## Content Sections

Content falls into three categories:

### 1. Fully Generated (from YAML data)
Pages built entirely from `data/` by Python generators + Jinja2 templates:

| Section | Generator | Output | Count |
|---------|-----------|--------|-------|
| Artist pages | `generate_bluesmen.py` | `/artist/{slug}/` | 422 |
| Album reviews | `generate_reviews.py` | `/artist/{a}/{alb}/` | 1,652 |
| News archive | `generate_news.py` | `/news/YYYY/MM/DD/storyN/` | 1,082 |
| Site updates | `generate_updates.py` | `/updates/YYYY/` | 968 |
| Forum | `generate_forum.py` | `/forum/topic{N}.html` | 5,230 |
| Photo galleries | `generate_galleries.py` | `/photo/YYYY/{slug}/` | 295 |
| ATB radio show | `generate_atb.py` | `/atb/{slug}/` | 349 |
| Homepage | `generate_homepage.py` | `/` + `/links/` | — |
| Calendar | `generate_calendar_page.py` | `/calendar/` | — |

### 2. Static Content (processed legacy HTML)
HTML from `content/` is copied to site with: analytics stripped, SSI includes resolved, links rewritten. Generator: `generate_content.py`.

Key static sections:
- `content/bluesnews/` → `/bluesnews/` (historical news with photos)
- `content/atb/` → `/atb/` (ATB archive pages, NOT episode pages)
- `content/beefheart/` → `/beefheart/`
- `content/ethnotrip/` → `/ethnotrip/`
- `content/zappazuhoi/` → `/zappazuhoi/`
- `content/artist/` → artist bio sub-pages (bio.htm, etc. linked from artist pages)
- `content/band/`, `content/efes/`, `content/nbf/` → festival/band sections
- `content/andrey/` → `/andrey/` (memorial page, listed in `static_sections`)
- `content/arc/` → `/arc/` (archive history article, listed in `static_sections`)

### 3. Pre-built JSON (client-side JS)
Built by `generate_data_json.py` → `bluesru-site/data/`:
- `data/calendar.json` — events indexed by MM-DD, loaded by `calendar.js`
- `data/artists/{slug}.json` — per-artist album list, loaded by `bluesmen.js`

---

## URL Conventions

- Slugs: lowercase, dashes, ASCII (`james-cotton`, not `James_Cotton`)
- Directory indexes: `index.html` always (never `default.htm`)
- `default.htm` / `default.html` → rename to `index.html` when copying to content/

**Artist pages**: `/artist/{slug}/` (e.g., `/artist/albert-collins/`)
- Legacy `/bluesmen/*` → `/artist/:splat` catch-all in `_redirects`

**Album pages**: `/artist/{artist-slug}/{album-slug}/`
- Album slug has artist prefix stripped: `/artist/albert-collins/cold-snap/` (not `albert-collins-cold-snap`)
- Helper: `_strip_artist_prefix(artist_slug, album_slug)` in `generate_shared.py`

**Forum topics**: `/forum/topic{N}.html` (flat files, no slash, no dash)
- Server rewrite: `/forum/topic{N}` → `/forum/topic{N}.html`
- Forum index pagination: `/forum/page2.html` (not `/forum/page2/`)

**Photo galleries**: `/photo/{year}/{canonical-date}-{slug}/`
- Example: `/photo/2022/2022-03-19-kaverkin/`

**ATB episodes**: `/atb/{slug}/`
- Slug generated from date + title

**aspx URLs**: Never served as HTML. All have 301 redirects in `_redirects`.
- `albumview.aspx?cdid=N` → `/artist/{a-slug}/{alb-slug}/`
- `artistview.aspx?aid=N` → `/artist/{slug}/`

---

## SSI Include Resolution

Legacy HTML files use `<!--#include virtual="..."--> ` directives. These are resolved at generation time by `resolve_include(vpath, source_dir, source_root)` in `generate_shared.py`.

**Resolution order**:
1. `bluesru-arc/content/` (encoding-corrected versions preferred)
2. Raw source dirs (readonly, encoding may be win-1251)

**Special cases**:
- `/footer.inc` → replaced with archive footer from `bluesru-arc/includes/footer.inc`
- Relative includes (e.g., `handy.inc` next to `handy/` pages) are supported
- Analytics/ad includes listed in `DROP_INCLUDES` are silently dropped

**Dropped includes** (list in `generate_shared.py`):
- `liveinternet*.inc`, `spylog*.inc`, any ad/banner includes

**Rule**: `footer.inc` must NEVER be dropped — it provides site navigation.

---

## HTML Processing Pipeline

Every legacy HTML file passes through `process_html()` in `generate_shared.py`:

```
1. strip_analytics()     Remove LiveInternet, Yandex.Metrika, Google Analytics, ad scripts
2. Strip ASP tags        Remove <asp:...>, <% %> blocks (re.DOTALL for multiline)
3. resolve_includes()    Replace <!--#include virtual="..."--> with actual HTML
4. _rewrite_links()      Apply _redirects rules + normalize internal links
                         Also strips http://blues.ru domain prefix from absolute internal URLs
5. (section-specific)    rewrite_artist_links(), rewrite_gallery_img_src(), etc.
```

**Encoding**: All source files are windows-1251. `read_file()` tries UTF-8 first (already-converted files), then win-1251, then Latin-1. Never use chardet.

---

## Redirect System

Two mechanisms, applied in order:

### 1. `_redirects` (build-time + serve-time)
Cloudflare Pages redirect rules. Parsed by both `generate_shared.py` and `serve.py`.

Format: `FROM_PATH [?QUERY] TO_PATH STATUS_CODE`

Types:
- Exact: `/review/default.aspx /review/ 301`
- Wildcard: `/bluesmen/* /artist/:splat 301`
- Query-string: `/data/albumview.aspx?cdid=123 /artist/a-slug/alb-slug/ 301`

### 2. `data/link_fixes.yaml` (postprocess only)
Dead internal links that have no redirect. Applied by `postprocess_dead_links()` (make postprocess).

Dead links styled: `class="dead-link"` + `data-dead-href` + `href="#"`

**Rule**: Run `make postprocess` after any change to `_redirects` or `link_fixes.yaml`.

**Auditing**: `tools/validate/audit_links.py` checks all links in generated site and outputs updated `link_fixes.yaml`. Currently: 0 broken links.

---

## Media & R2

### Media Structure

```
bluesru-media/          Local copy (not committed)
├── photo/              Gallery photos, organized by gallery slug
│   └── 2022/2022-03-19-kaverkin/content/  ← images live in content/ subdir
├── atb/                Radio show MP3 files
│   ├── ATB_YYYYMMDD_Title.mp3
│   └── {subdir}/
└── (other sections)

bluesru-media.cache/    Thumbnail cache (not committed)
└── photo/              Mirrors bluesru-media/photo/ tree
    └── **/*-400w.jpg   400px-wide thumbnails (generated by make thumbs)
```

### R2 Bucket Layout

R2 bucket: `r2:bluesru-media` (via `rclone`)

```
bluesru-media/          ← synced from local bluesru-media/
bluesru-media.cache/    ← synced from local bluesru-media.cache/
```

Access URL: `https://internal-media.blues.ru/` (via CF Pages Worker)

The `functions/_middleware.js` Worker intercepts requests to `/bluesru-media/*` and proxies them from R2. This is how the deployed site serves photos and MP3s without committing large binaries.

### Thumbnail Pipeline

Thumbnails are `-400w.jpg` files, generated from full-size photos.

```bash
make thumbs          # generate all missing thumbnails (incremental, uses macOS sips)
make thumbs-dry      # preview what would be generated
make push-cache      # sync cache to R2
```

Script: `scripts/thumbs.py`
- Source: `bluesru-media/photo/**/*.jpg`
- Output: `bluesru-media.cache/photo/**/*-400w.jpg`
- Naming: `{stem}-400w.jpg` (same directory, same name + width suffix)
- Incremental: skips existing thumbnails

`serve.py` resolves thumbnail requests: checks `SITE` → `MEDIA` → `CACHE` directories.

### Custom R2 Path Remaps

Some ATB subdirs have different URL paths vs physical R2 paths:
- `/atb/excerpts/` → R2 path differs
- `/atb/kalachev-kostin-show/` → R2 path differs

See `media-manifest.json` (repo root) for full inventory and custom prefix overrides.

---

## Templates Reference

All templates are Jinja2 (`.j2`) in `templates/`. Global variables available in all:

```python
footer        # HTML from includes/footer.inc — site navigation
donate        # HTML from includes/donate.inc — donation buttons
ga_snippet    # Google Analytics tracking snippet
site_css_tag  # <link rel="stylesheet" href="/css/site.css">
```

| Template | Section | Key variables |
|----------|---------|---------------|
| `albumview.html.j2` | Album review | `album`, `artist_name`, `cover_url`, `reviews[]`, `streaming_links` |
| `bluesmen_list.html.j2` | Artist index | `artists[]`, `letters` |
| `forum_index.html.j2` | Forum listing | `topics[]`, `page`, `has_next` |
| `forum_topic.html.j2` | Forum topic | `topic`, rendered via `render_topic()` |
| `atb_index.html.j2` | ATB index | `episodes[]` |
| `atb_episode.html.j2` | ATB episode | `show`, `files[]`, `summary` |
| `gallery.html.j2` | Photo gallery | `photos[]`, `photos_json`, `title`, `date` |
| `photo_index.html.j2` | Gallery index | `galleries[]`, grouped by year |
| `news_list.html.j2` | News archive | `items[]`, `by_year` |
| `updates_list.html.j2` | Updates | `items[]`, `by_year` |
| `review_index.html.j2` | Review index | `reviews[]`, paginated monthly |
| `homepage.html.j2` | Homepage | `blues_news[]`, `latest_atb[]`, `latest_updates[]` |
| `calendar_index.html.j2` | Calendar | `events{}` by MM-DD |

---

## Key Shared Functions

All in `generate_shared.py`. Import with: `from generate_shared import ...`

### Data Loaders
```python
load_artists()             # → dict[id → artist_dict]; source: data/artists.yaml
load_albums()              # → dict[id → album_dict]; source: data/albums/**/*.yaml
# Albums already contain reviews[] — no separate reviews loader needed
```

### HTML Helpers
```python
process_html(content, source_dir, source_root, ...)  # Full processing pipeline
resolve_include(vpath, source_dir, source_root)       # Resolve SSI include
strip_analytics(content)                              # Remove tracking code
_rewrite_links(content)                               # Apply redirects + link fixes
```

### URL Helpers
```python
_strip_artist_prefix(artist_slug, album_slug)         # Remove artist prefix from album slug
streaming_links_html(slug, kind='album'|'artist')     # Pipe-separated streaming links HTML
cover_url_for_asin(asin)                              # Local cache or Amazon URL
```

### Forum Helpers
```python
sanitize_forum_html(text)          # Escape HTML, preserve allowed tags + char refs
render_post_html(post, ...)        # Render single post
render_topic_html(topic, ...)      # Render full/preview topic
_forum_visible_topics()            # Filter spam/all-deleted topics
_autolink_bare_urls(text)          # Add <a> tags to bare URLs (rel=nofollow)
```

### Review Marks
Mark is integer 0–20. Rendered as `@` symbols: `mark // 2` full `@`, `mark % 2` half `@`.
Template: `'@' * full + ('+' if half else '')` (+ is half-mark).

---

## Forum Build Details

Forum is the largest section (5,230 topics, 39 MB YAML). Parallel sharding speeds it up:

```bash
make forum-plan        # Split topics into .forum-shards/shard-{0..7}.txt
# Then run in parallel:
make forum-index       # Generate /forum/index.html + /forum/page*.html
make forum-shard-0     # Generate topics from shard 0
make forum-shard-1     # ...
# Or all at once:
make -j8 $(addprefix forum-shard-, 0 1 2 3 4 5 6 7)
```

Topic YAML path pattern: `data/forum/topics/YYYY/MM/YYYY-MM-DD-topic-{id}.yaml`

Spam filtering:
- `data/forum/spam-ids.yaml` — individual post IDs to suppress
- Topics where ALL posts are deleted/spam are hidden from index
- Deleted posts are fully hidden (no name/subject shown)

---

## Gallery System

### Gallery Types

| Type | Source | Generation |
|------|--------|------------|
| `lightroom` | Images in `{path}/content/` subdir | Generated from YAML |
| `mts` | Images in `{path}/content/` subdir | Generated from YAML |
| `custom` | Static HTML in `content/` | Served as-is |

For lightroom/mts galleries, photo file paths in YAML are relative. When building photo cards: `f"{gallery_path}/content/{photo.file}"`.

`exclude: true` in gallery YAML → hidden from index, not generated.

### Gallery URLs
`/photo/{year}/{canonical-date}-{slug}/` (e.g., `/photo/2022/2022-03-19-kaverkin/`)

### Stale Cleanup
`generate_photo_index()` removes `bluesru-site/photo/YYYY/*/` dirs not in current valid URL set. Exception: `nbf-*` dirs are generated separately.

---

## Streaming Links

Stored directly in artist/album YAML files (not separate files):
- Artists: `spotify_id`, `apple_music_id` in `data/artists.yaml`
- Albums: `apple_music_id`, `spotify_id`, `deezer_id`, `ytmusic_id`, `youtube_video_id`, `youtube_playlist_id` in each album YAML

URL templates and rendering: `streaming_links_html(slug, kind)` in `generate_shared.py`.

Label on album pages: **"Альбом на:"** (not "Слушать:"). Amazon comes first if `asin` exists.

Coverage: 86% albums (1,435/1,652). All 422 artists have `spotify_id`.

---

## ATB Radio Show

- Source: `data/atb/episodes.yaml` (349 episodes)
- MP3 files: `bluesru-media/atb/` (served from R2)
- Multi-part episodes: grouped by `(date, subdir)` → both parts on one page with `<audio>` players labeled "Часть 1", "Часть 2"
- Transcripts: Markdown with `<a id="tN"></a>` timecode anchors in `data/atb/transcripts/`
- Archive page: `content/atb/ATBr-index2000.htm` (renamed from index.htm to avoid collision)

---

## Test Server

```bash
make serve     # starts at http://localhost/ or http://a.blues.ru/ (local DNS)
```

`scripts/serve.py` serves `bluesru-site/` with:
- Redirect rule application (parses `_redirects`)
- `/forum/topic{N}` → `/forum/topic{N}.html` rewrite
- Directory index resolution (`/foo/` → `/foo/index.html`)
- HTTP Range requests (for audio seeking in MP3 players)
- Media fallback: SITE → MEDIA (`bluesru-media/`) → CACHE (`bluesru-media.cache/`)
- Correct `Content-Type: text/html; charset=utf-8`

---

## Tools Directory (`tools/`)

Utility scripts for data enrichment, not part of the normal build. Run ad hoc when needed.

### `tools/streaming/` — Music Service APIs
- `fetch_spotify_artists.py` — Fetch Spotify artist IDs via API → updates `data/artists.yaml`
- `find_music_links.py` — Find albums on Spotify + Apple Music → updates album YAML files
- `add_spotify_links.py` — Add Spotify links using LLM matching (ANTHROPIC_API_KEY required)
- `match_music_links.py` — Match albums to Deezer/Spotify via artist catalog + LLM
- `find_youtube_links.py` — Find YouTube Music IDs + YouTube bootleg videos (uses yt-dlp)
- `cache_amazon_covers.py` — Download Amazon cover images → `covers/{asin}.jpg`

Requires: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` (Spotify), `ANTHROPIC_API_KEY` (LLM matching)

### `tools/enrichment/` — LLM Data Enrichment
- `enrich_galleries.py` — Add canonical_date, clean_title, slug, description via LLM
- `rename_galleries.py` — Rename gallery YAML files to clean English slugs via Claude API
- `rename_news.py` — Rename news MD files to clean English slugs
- `rename_announcements.py` — Rename announcement MD files to clean English slugs

Requires: `ANTHROPIC_API_KEY`

### `tools/audio/` — ATB Transcription Pipeline
- `transcribe_atb.py` — Transcribe MP3s via mlx-whisper (Apple Silicon required)
- `postprocess_atb.py` — Clean ASR output via Claude API; output → `data/atb/transcripts/*.md`
- `enrich_atb.py` — Generate episode summaries + artist tags via Claude API
- `rebuild_atb_timing.py` — Rebuild transcript timing without Claude (fixes timing drift)
- `run_all_atb.py` — Full pipeline orchestrator (transcribe → postprocess)
- `eval_atb.py` — Evaluate transcript quality vs golden reference

Requires: mlx-whisper (Apple Silicon), `ANTHROPIC_API_KEY`

### `tools/spam/` — Forum Spam Detection
- `detect_spam.py` — Classify forum posts via Claude Haiku Batch API → `data/forum/spam-ids.yaml`
- `classify_spam.py` — Single-request classification via Claude Sonnet (large context)
- `purge_spam_posts.py` — Remove confirmed spam from forum YAML files

Requires: `ANTHROPIC_API_KEY`

### `tools/gallery/` — Gallery Data Tools
- `reorganize_albums.py` — Move `data/albums/{slug}.yaml` → `data/albums/{artist-slug}/{slug}.yaml`

### `tools/validate/` — Link Auditing
- `audit_links.py` — Check all internal links in generated site; output `data/link_fixes.yaml`

---

## Common Gotchas

1. **`make postprocess` after HTML changes** — any new content or link change requires a postprocess run; it rewrites ~5,700 HTML files globally.

2. **Forum sort by integer ID** — topics sorted by `topic_id` as integer descending. String sort breaks order.

3. **default.htm → index.html** — normalize on copy; never leave default.htm in generated output.

4. **Album slug has artist prefix stripped** — `/artist/albert-collins/cold-snap/` not `albert-collins-cold-snap/`. Use `_strip_artist_prefix()`.

5. **Gallery photos are in `content/` subdir** — when building photo cards from YAML: `f"{gpath}/content/{photo.file}"`.

6. **Gallery dark theme breadcrumbs** — use `color: #aaa`, links `color: #7ab4e8`. Dark colors invisible on dark background.

7. **Encoding: always windows-1251 for legacy files** — never chardet. `read_file()` handles fallback.

8. **CF Pages build** — On CF Pages, `CF_PAGES=1` is set; output goes to `bluesru-arc/bluesru-site/` (inside repo) so wrangler can find `pages_build_output_dir`.

9. **Two news streams** — "Новости blues.ru" (`data/updates/`) ≠ "Блюзовые новости" (`data/news/`). Updates are site announcements; news is archive-only blues journalism.

12. **Two news streams** — "Новости blues.ru" (`data/updates/`) ≠ "Блюзовые новости" (`data/news/`). Updates are site announcements; news is archive-only blues journalism.
