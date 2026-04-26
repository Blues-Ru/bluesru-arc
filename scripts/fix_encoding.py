#!/usr/bin/env python3
"""
Fix encoding corruption in blues-ru/ source files.

237 files were misidentified as Arabic (cp1256) by chardet during initial
UTF-8 conversion. Fix: restore from git, decode as windows-1251, save as UTF-8.

Run from /Users/fedor/bluesru/
"""

import subprocess
import re
from pathlib import Path

import os
ARC = Path(__file__).resolve().parent.parent
_ws = Path(os.environ.get('BLUESRU_ROOT', str(ARC.parent)))
BLUES_RU = _ws / "blues-ru"

# Pattern that identifies corrupted files: Arabic Presentation Forms (U+FE00-FEFF)
# encoded as EF B8-BF in UTF-8 — these should not appear in Russian web pages
UTF8_BOM = b'\xef\xbb\xbf'
# Arabic Presentation Forms (U+FE00-FEFF) in UTF-8, excluding BOM (U+FEFF = EF BB BF)
ARABIC_PATTERN = re.compile(b'\xef[\xb8-\xbf][\x80-\xbf]')

def has_real_arabic(data):
    """True if file has Arabic Presentation Forms that are NOT just the UTF-8 BOM."""
    # Strip leading BOM for the check
    check = data[3:] if data.startswith(UTF8_BOM) else data
    return bool(ARABIC_PATTERN.search(check))

def get_corrupted_files():
    """Find all files with Arabic Presentation Forms (encoding corruption)."""
    corrupted = []
    for fpath in BLUES_RU.rglob('*'):
        if not fpath.is_file():
            continue
        if fpath.suffix.lower() not in ('.htm', '.html', '.inc', '.aspx', '.ascx', '.xml'):
            continue
        if '.git' in fpath.parts:
            continue
        data = fpath.read_bytes()
        if has_real_arabic(data):
            corrupted.append(fpath)
    return corrupted


def restore_and_convert(fpath):
    """Restore from git, decode as windows-1251, save as UTF-8."""
    rel = fpath.relative_to(BLUES_RU)

    # Get original bytes from git
    result = subprocess.run(
        ['git', 'show', f'HEAD:{rel}'],
        capture_output=True,
        cwd=BLUES_RU
    )
    if result.returncode != 0:
        return False, f"git show failed: {result.stderr.decode()[:100]}"

    orig_bytes = result.stdout
    # Strip UTF-8 BOM if present
    if orig_bytes.startswith(UTF8_BOM):
        orig_bytes = orig_bytes[3:]

    # Check if original is already UTF-8 (some files were already UTF-8 in git)
    try:
        text = orig_bytes.decode('utf-8')
        encoding_used = 'utf-8 (original)'
    except UnicodeDecodeError:
        try:
            text = orig_bytes.decode('windows-1251')
            encoding_used = 'windows-1251'
        except UnicodeDecodeError:
            return False, "could not decode as utf-8 or windows-1251"

    # Update meta charset declaration if present
    text = re.sub(
        r'(charset\s*=\s*)["\']?windows-1251["\']?',
        r'\1utf-8',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'(charset\s*=\s*)["\']?cp1251["\']?',
        r'\1utf-8',
        text,
        flags=re.IGNORECASE
    )

    fpath.write_text(text, encoding='utf-8')
    return True, encoding_used


def main():
    print("Scanning for corrupted files...")
    corrupted = get_corrupted_files()
    print(f"Found {len(corrupted)} corrupted files")

    fixed = 0
    failed = []

    for fpath in sorted(corrupted):
        rel = fpath.relative_to(ROOT)
        ok, detail = restore_and_convert(fpath)
        if ok:
            print(f"  Fixed ({detail}): {rel}")
            fixed += 1
        else:
            print(f"  FAILED: {rel} — {detail}")
            failed.append(str(rel))

    print(f"\nFixed: {fixed}/{len(corrupted)}")
    if failed:
        print(f"Failed ({len(failed)}):")
        for f in failed:
            print(f"  {f}")

    # Verify
    remaining = get_corrupted_files()
    print(f"\nRemaining corrupted: {len(remaining)}")
    if remaining:
        for f in remaining[:10]:
            print(f"  {f.relative_to(ROOT)}")


if __name__ == '__main__':
    main()
