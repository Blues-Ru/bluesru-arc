#!/bin/bash
# Build bluesru-arc → bluesru-site/.
# Run from the bluesru-arc/ repo root (or any directory — script is self-locating).
set -e

# Locate repo root regardless of where this script is invoked from
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SITE_DIR="${BLUESRU_SITE:-$ARC_ROOT/../bluesru-site}"

cd "$ARC_ROOT"

# ── Backup existing output ────────────────────────────────────────────────────
if [ -d "$SITE_DIR" ]; then
    STAMP=$(date +%Y%m%d)
    BACKUP="${SITE_DIR}-$STAMP"
    i=1
    while [ -d "$BACKUP" ]; do
        BACKUP="${SITE_DIR}-${STAMP}-$i"
        i=$((i+1))
    done
    echo "Archiving existing output → $BACKUP/"
    mv "$SITE_DIR" "$BACKUP"
fi

mkdir -p "$SITE_DIR"

echo ""
echo "=== Blues.Ru Archive Build ==="
echo "  Repo:   $ARC_ROOT"
echo "  Output: $SITE_DIR"
echo ""

PY="python3"
S="$SCRIPT_DIR"
export BLUESRU_SITE="$SITE_DIR"

echo "1. Fix encoding (restore corrupted Win-1251 files from git)..."
$PY "$S/fix_encoding.py"

echo ""
echo "2. Generate _redirects and Cloudflare CSV..."
$PY "$S/generate_redirects.py"

echo ""
echo "3. Generate JSON data files (calendar, news, artist albums)..."
$PY "$S/generate_data_json.py"

echo ""
echo "4. Generate homepage + links pages..."
$PY "$S/generate_homepage.py"

echo ""
echo "5. Process static content (bluesnews, atb, beefheart, etc.)..."
$PY "$S/generate.py" --section content

echo ""
echo "6. Generate artist pages..."
$PY "$S/generate.py" --section bluesmen

echo ""
echo "7. Generate review (albumview) pages..."
$PY "$S/generate.py" --section reviews

echo ""
echo "8. Generate news archive..."
$PY "$S/generate.py" --section news

echo ""
echo "9. Generate forum pages..."
$PY "$S/generate.py" --section forum

echo ""
echo "9b. Generate site updates..."
$PY "$S/generate.py" --section updates

echo ""
echo "10. Generate calendar page..."
$PY "$S/generate_calendar_page.py"

echo ""
echo "11. Generate review RSS feed..."
$PY "$S/generate_rss.py"

echo ""
echo "12. Generate ATB (Весь этот блюз) section..."
$PY "$S/generate.py" --section atb

echo ""
echo "13. Generate anagrams page..."
$PY "$S/generate_anagrams.py"

echo ""
echo "14. Generate gallery pages..."
$PY "$S/generate.py" --section galleries

echo ""
echo "14b. Generate NBF photo galleries..."
$PY "$S/generate.py" --section nbf

echo ""
echo "14c. Generate photo index..."
$PY "$S/generate.py" --section photo

echo ""
echo "15. Post-process dead links across all generated HTML..."
$PY "$S/generate.py" --section postprocess

echo ""
echo "=== Build complete ==="
echo ""
du -sh "$SITE_DIR" 2>/dev/null || echo "Output dir not found: $SITE_DIR"
echo "HTML pages:"
find "$SITE_DIR" -name "*.html" -o -name "*.htm" 2>/dev/null | wc -l
