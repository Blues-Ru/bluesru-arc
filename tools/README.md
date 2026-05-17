# tools/

Maintenance and data-processing scripts that are **not** part of the
site build. Each is invoked manually when there's new input to process
or curated data to enrich.

The site build (`make build`, `scripts/generate*.py`) **never** runs
anything from here. Conversely, nothing here should overwrite committed
files that the build consumes (`data/*.yaml`, `templates/`, root
`_redirects`, etc.) — these write *enrichments* (new IDs, new transcripts,
new redirects) that are then reviewed and committed by a human.

## Subdirs

| Dir | Purpose | Re-run when |
|---|---|---|
| `audio/` | ATB radio episode transcription, summary generation, timing rebuilds | new MP3s land in source |
| `streaming/` | Lookups against Spotify / Apple Music / Discogs / YouTube; cover-art caching | new artists or albums registered |
| `enrichment/` | Gallery / news / announcement renames and metadata fills | bulk renames needed on a section |
| `gallery/` | Photo gallery album reorganization | one-off album restructuring |
| `spam/` | Forum spam classification / detection / purging | new forum import or spam wave |
| `validate/` | Site-wide link auditor (`audit_links.py`) | after structural changes |

## Adding new tools

Drop the script in the most appropriate subdir (or create a new one with
a clear theme). Conventions:

- **No script under `scripts/`** unless it's wired into `Makefile` or
  `scripts/generate.py`. `scripts/` is reserved for the build pipeline.
- **Don't overwrite curated files**: if a tool needs to suggest a
  change to `_redirects`, `data/artists.yaml`, etc., emit a diff or a
  side-file and let a human apply it. The committed file should always
  reflect human judgement, not the last `tools/` run.
- **One-shot fixups don't live here**: renames, dedupes, and migrations
  that run once and never again should be written as ad-hoc code in
  `/tmp/`, applied, then discarded. The committed artifact is the
  resulting data, not the script that produced it.
