PYTHON     = python3
SCRIPTS    = scripts
ROOT       = /Users/fedor/bluesru
SITE       = $(ROOT)/bluesru-site
MEDIA      = $(ROOT)/bluesru-media
CACHE      = $(ROOT)/bluesru-media.cache
R2         = r2:bluesru-media
SHARD_DIR  = .forum-shards
NSHARDS    = 8
SHARDS     = 0 1 2 3 4 5 6 7

# On CF Pages BLUESRU_ROOT is not set; generate.py falls back to repo-relative paths
RUN = $(if $(wildcard $(ROOT)),BLUESRU_ROOT=$(ROOT),) $(PYTHON)

# ── Dependencies ─────────────────────────────────────────────────────────────

deps: .deps-stamp

.deps-stamp: requirements.txt
	pip install -q -r requirements.txt
	@touch $@

# ── Sequential build (default) ───────────────────────────────────────────────
#
# Runs all sections in dependency order, with site backup before starting.
# Use 'make build-parallel' for faster parallel execution.

build: deps backup homepage content updates data news anagrams artists reviews \
       atb calendar photo-pages photo-index forum-authors forum postprocess sitemap deploy

backup:
	@if [ -d "$(SITE)" ]; then \
	    STAMP=$$(date +%Y%m%d); BACKUP="$(SITE)-$$STAMP"; I=1; \
	    while [ -d "$$BACKUP" ]; do BACKUP="$(SITE)-$${STAMP}-$$I"; I=$$((I+1)); done; \
	    echo "Archiving existing site → $$BACKUP/"; \
	    mv "$(SITE)" "$$BACKUP"; \
	fi

# ── Parallel build ────────────────────────────────────────────────────────────
#
# DAG:
#   Phase 1 (parallel): content artists news reviews atb updates homepage
#                       data photo-pages forum-index forum-plan
#   Phase 2 (parallel): photo-index  forum-shard-0..N  (after photo-pages / forum-plan+index)
#   Phase 3:            postprocess
#   Phase 4:            deploy
#
# Usage: make -j16 build-parallel

build-parallel: deps postprocess deploy

deploy: sitemap

sitemap: postprocess
	$(RUN) $(SCRIPTS)/generate_sitemap.py

postprocess: _phase2

_phase2: photo-index $(addprefix forum-shard-, $(SHARDS))

# Phase 1 — all independent sections + forum prep
_phase1: content artists news reviews atb updates homepage data calendar \
         anagrams photo-pages forum-authors forum-index forum-plan

postprocess: _phase1

# ── Individual sections ───────────────────────────────────────────────────────

content:
	$(RUN) $(SCRIPTS)/generate_content.py

artists:
	$(RUN) $(SCRIPTS)/generate_artists.py

news:
	$(RUN) $(SCRIPTS)/generate_news.py

reviews:
	$(RUN) $(SCRIPTS)/generate_reviews.py

atb:
	$(RUN) $(SCRIPTS)/generate_atb.py

updates:
	$(RUN) $(SCRIPTS)/generate_updates.py

homepage:
	$(RUN) $(SCRIPTS)/generate_homepage.py

postprocess:
	$(RUN) $(SCRIPTS)/generate.py --section postprocess

deploy:
	$(RUN) $(SCRIPTS)/generate.py --section deploy

calendar:
	$(RUN) $(SCRIPTS)/generate_calendar.py

anagrams:
	$(RUN) $(SCRIPTS)/generate_anagrams.py

photo-pages:
	$(RUN) $(SCRIPTS)/generate_photos.py --section photo-pages

photo-index:
	$(RUN) $(SCRIPTS)/generate_photos.py --section photo-index

photos: photo-pages photo-index

data:
	$(RUN) $(SCRIPTS)/generate_data.py

# ── Forum ─────────────────────────────────────────────────────────────────────

forum-authors:
	$(RUN) $(SCRIPTS)/generate_forum_authors.py

forum:
	$(RUN) $(SCRIPTS)/generate_forum.py

forum-plan:
	$(RUN) $(SCRIPTS)/forum_plan.py --nshards $(NSHARDS) --out $(SHARD_DIR)

forum-index:
	$(RUN) $(SCRIPTS)/generate_forum.py --section forum-index

$(addprefix forum-shard-, $(SHARDS)): forum-shard-%: forum-index forum-plan
	$(RUN) $(SCRIPTS)/generate_forum.py --section forum-topics \
	    --shard-file $(SHARD_DIR)/shard-$*.txt

# ── Dev ───────────────────────────────────────────────────────────────────────

serve:
	$(RUN) $(SCRIPTS)/serve.py

thumbs:
	$(RUN) $(SCRIPTS)/thumbs.py

thumbs-dry:
	$(RUN) $(SCRIPTS)/thumbs.py --dry-run

# ── Deploy ────────────────────────────────────────────────────────────────────

push:
	git push

push-media:
	rclone sync $(MEDIA)/ $(R2)/bluesru-media/

push-cache:
	rclone sync $(CACHE)/ $(R2)/bluesru-media.cache/

push-all: push-media push-cache push

.PHONY: deps build build-parallel backup _phase1 _phase2 \
        content artists news reviews atb updates homepage data \
        calendar anagrams photo-pages photo-index photos postprocess sitemap deploy \
        forum-authors forum forum-plan forum-index \
        $(addprefix forum-shard-, $(SHARDS)) \
        serve thumbs thumbs-dry \
        push push-media push-cache push-all
