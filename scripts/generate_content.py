#!/usr/bin/env python3
"""Copy and post-process static content sections."""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_shared import (
    ARC,
    CAL_IMGS,
    CONTENT,
    SITE,
    _build_custom_gallery_media_map,
    _copy_dir,
    _copy_section,
    _gallery_dir_prefixes,
    process_html,
    read_file,
)


def generate_content():
    print("Processing static content from bluesru-arc/content/...")

    if not CONTENT.exists() or not any(CONTENT.iterdir()):
        print("  ERROR: bluesru-arc/content/ is empty. Run populate.py first.")
        return

    external_sections = [
        'beefheart', 'zappazuhoi', 'bluesnews', 'atb',
    ]
    gallery_skip = _gallery_dir_prefixes()
    custom_gallery_media = _build_custom_gallery_media_map()

    for name in external_sections:
        src = CONTENT / name
        if not src.exists():
            print(f"  {name}/: not in content/, skipping")
            continue
        dst = SITE / name
        src_root = src
        skip = gallery_skip if name == 'bluesnews' else None
        media_map = custom_gallery_media if name == 'bluesnews' else None
        count = _copy_section(src, dst, src_root, skip_paths=skip, media_gallery_map=media_map)
        if not (dst / 'index.html').exists():
            for candidate in ['default.htm.1', 'default.html.1']:
                fallback = src / candidate
                if fallback.exists():
                    content = read_file(fallback)
                    if content:
                        content = process_html(content, src, src_root)
                        (dst / 'index.html').write_text(content, encoding='utf-8')
                        count += 1
                        print(f"    → {candidate} used as index.html")
                    break
        print(f"  {name}/: {count} files")

    # blues-calendar images → site/calendar/images/
    dst_cal = SITE / 'calendar' / 'images'
    dst_cal.mkdir(parents=True, exist_ok=True)
    cal_count = 0
    for img in CAL_IMGS.rglob('*'):
        if img.is_file() and '.git' not in img.parts:
            dst = dst_cal / img.relative_to(CAL_IMGS)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(img, dst)
            cal_count += 1
    print(f"  calendar/images/: {cal_count} images")

    static_sections = [
        'band', 'style', 'bsfest', 'bbkingfest', 'efes', 'nbf',
        'svalbard', 'nepal', 'august', 'handy', 'mojobook', 'book',
        'reading', 'vocabulary.htm', 'about.htm', 'label',
        'ww', 'club', 'stuff',
        'fest', 'article', 'harp', 'lessons', 'andrey', 'fedor', 'arc',
    ]
    sec_total = 0
    for section in static_sections:
        src = CONTENT / section
        if not src.exists():
            continue
        dst = SITE / section
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.suffix.lower() in ('.htm', '.html'):
                content = read_file(src)
                if content:
                    content = process_html(content, src.parent, CONTENT)
                    dst.write_text(content, encoding='utf-8')
                    sec_total += 1
            else:
                shutil.copy2(src, dst)
                sec_total += 1
        else:
            c = _copy_section(src, dst, CONTENT)
            sec_total += c
    print(f"  blues-ru sections/: {sec_total} files")

    _copy_dir(ARC / 'js',      SITE / 'js')
    _copy_dir(ARC / 'css',     SITE / 'css')
    _copy_dir(ARC / 'forum',   SITE / 'forum')
    _copy_dir(ARC / 'covers',  SITE / 'covers')
    _copy_dir(ARC / 'images',  SITE / 'images')
    (SITE / 'news' / 'images').mkdir(parents=True, exist_ok=True)
    _copy_dir(ARC / 'news' / 'images', SITE / 'news' / 'images')
    print("  assets: js/ css/ forum/ covers/ images/ news/images/ copied")


if __name__ == '__main__':
    generate_content()
