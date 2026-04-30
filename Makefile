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

# ── Full sequential build (default) ──────────────────────────────────────────

build: deps
	bash $(SCRIPTS)/build.sh

# ── Parallel build ────────────────────────────────────────────────────────────
#
# DAG:
#   Phase 1 (parallel): content bluesmen news reviews atb updates homepage
#                       data galleries forum-index forum-plan
#   Phase 2 (parallel): photo  forum-shard-0..N  (after galleries / forum-plan+index)
#   Phase 3:            postprocess
#   Phase 4:            deploy
#
# Usage: make -j16 build-parallel

build-parallel: deps postprocess deploy

deploy: postprocess
postprocess: _phase2

_phase2: photo $(addprefix forum-shard-, $(SHARDS))

photo: galleries

$(addprefix forum-shard-, $(SHARDS)): forum-index forum-plan

# Phase 1 — all independent sections + forum prep
_phase1: content bluesmen news reviews atb updates homepage data galleries \
         forum-index forum-plan

postprocess: _phase1

# ── Individual sections ───────────────────────────────────────────────────────

content bluesmen news reviews atb updates homepage postprocess deploy:
	$(RUN) $(SCRIPTS)/generate.py --section $@

galleries:
	$(RUN) $(SCRIPTS)/generate.py --section galleries

photo:
	$(RUN) $(SCRIPTS)/generate.py --section photo

data:
	$(RUN) $(SCRIPTS)/generate_data_json.py

# ── Forum ─────────────────────────────────────────────────────────────────────

forum:
	$(RUN) $(SCRIPTS)/generate.py --section forum

forum-plan:
	$(RUN) $(SCRIPTS)/forum_plan.py --nshards $(NSHARDS) --out $(SHARD_DIR)

forum-index:
	$(RUN) $(SCRIPTS)/generate.py --section forum-index

forum-shard-%:
	$(RUN) $(SCRIPTS)/generate.py --section forum-topics \
	    --shard-file $(SHARD_DIR)/shard-$*.txt

# ── Dev ───────────────────────────────────────────────────────────────────────

serve:
	sudo $(RUN) $(SCRIPTS)/serve.py

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

.PHONY: deps build build-parallel _phase1 _phase2 \
        content bluesmen news reviews atb updates homepage data \
        galleries photo postprocess deploy \
        forum forum-plan forum-index \
        $(addprefix forum-shard-, $(SHARDS)) \
        serve thumbs thumbs-dry \
        push push-media push-cache push-all
