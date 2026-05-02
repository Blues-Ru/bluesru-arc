#!/usr/bin/env python3
"""
Post-process ATB transcription JSON using Claude API.

Pipeline:
  1. Build annotated text: speech blocks tagged [T:MM:SS], music gaps tagged [MUSIC: A–B]
  2. Claude: clean Russian, fix ASR errors, keep [T:...] and [MUSIC:...] markers intact
  3. Python: merge adjacent [MUSIC] blocks (song pauses), insert <a id="..."> anchors

Outputs: bluesru-arc/data/atb/transcripts/{slug}.md  (one per file, committed)
JSONs:   extracted-data/atb/transcripts/{slug}.json (dev-only, not committed)
JSONs are preserved separately for re-prompting.

Usage:
    python3 postprocess_atb.py <slug_or_json> [...]
    python3 postprocess_atb.py atb-2014-10-27-guy-davis
"""

import json
import os
import re
import sys
from pathlib import Path

import anthropic

ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
TRANSCRIPT_DIR = WORKSPACE / "extracted-data/atb/transcripts"  # JSONs (dev-only)
TRANSCRIPT_MD_DIR = ARC / "data/atb/transcripts"  # MDs (committed)
SONG_GAP = 25.0   # seconds — gap >= this between speech segments → song playing
MODEL = "claude-sonnet-4-6"


def fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def time_to_secs(t: str) -> int:
    parts = list(map(int, t.split(":")))
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


# Two categories of hallucination, used only for [T:] timestamp selection.
# NOT used to filter segments from Claude (they all still reach Claude).
#
# MUSIC_MARKER: Whisper generates these while music is actively playing.
#   Seeing one means we're still in song territory — English following it is song tail.
# PURE_ARTIFACT: Whisper generates these in silence or at transitions.
#   Seeing one clears the "in song" state — English following it may be real speech.
_MUSIC_MARKER_RE = re.compile(r'динамичная\s+музыка|играет\s+музыка', re.IGNORECASE)
_PURE_ARTIFACT_RE = re.compile(r'субтитр\w*|dimaTorzok|torzok|переводчик', re.IGNORECASE)
_BUILD_HALLU_RE = re.compile(
    _PURE_ARTIFACT_RE.pattern + '|' + _MUSIC_MARKER_RE.pattern, re.IGNORECASE
)


def build_annotated(segments: list) -> str:
    """Build input text for Claude.

    Speech blocks start with [T:MM:SS] on its own line, followed by
    timestamped lines. Music gaps are [MUSIC: MM:SS–MM:SS].
    Claude is instructed to preserve [T:...] and [MUSIC:...] exactly.

    All segments (including hallucinations) are sent to Claude so it can
    delete them and trigger the downstream music-merging logic.

    [T:] timestamp selection:
    - SONG_GAP (≥25s) sets in_song_gap=True: English non-hallu after this are song tail.
    - MUSIC_MARKER (e.g. ДИНАМИЧНАЯ МУЗЫКА) keeps in_song_gap=True.
    - PURE_ARTIFACT (e.g. DimaTorzok) clears in_song_gap: transition boundary,
      English following it may be the host naming a song.
    - Any Cyrillic non-hallu segment clears in_song_gap and anchors speech_start.
    - Repetition artifact: same short phrase 2+ times in a row → treated as music artifact
      (Whisper hallucinating e.g. "Да." repeatedly during music).

    MUSIC block start uses clean_prev_end (last Cyrillic non-artifact segment end)
    rather than prev_end, so DimaTorzok / song-tail fragments don't push the MUSIC
    start timestamp deeper into the music.
    """
    parts = []
    prev_end = 0.0
    clean_prev_end = 0.0   # end of last Cyrillic non-artifact non-repetition segment
    speech_lines: list[str] = []
    speech_start: float | None = None
    block_start: float | None = None
    in_song_gap = False  # True while we're in song-tail territory
    last_text_norm: str | None = None  # for repetition detection
    repeat_streak = 0

    def flush():
        nonlocal speech_lines, speech_start, block_start, in_song_gap
        nonlocal last_text_norm, repeat_streak
        if speech_lines:
            ts = speech_start if speech_start is not None else block_start
            parts.append(f"[T:{fmt_time(ts)}]\n" + "\n".join(speech_lines))
            speech_lines = []
            speech_start = None
            block_start = None
            in_song_gap = False
            last_text_norm = None
            repeat_streak = 0

    for seg in segments:
        start, end = seg["start"], seg["end"]
        text = seg["text"].strip()
        gap = start - prev_end

        if gap >= SONG_GAP:
            music_start = clean_prev_end if clean_prev_end > 0 else prev_end
            flush()
            parts.append(f"[MUSIC: {fmt_time(music_start)}–{fmt_time(start)}]")
            in_song_gap = True
            clean_prev_end = 0.0  # reset: will re-anchor from first real content in new block
            last_text_norm = None
            repeat_streak = 0

        if text:
            if block_start is None:
                block_start = start

            is_music_marker  = bool(_MUSIC_MARKER_RE.search(text))
            is_pure_artifact = bool(_PURE_ARTIFACT_RE.search(text))
            is_build_hallu   = is_music_marker or is_pure_artifact

            # Repetition detection: same phrase 2+ times in a row → music artifact
            tnorm = text.lower().strip(".")
            if tnorm == last_text_norm:
                repeat_streak += 1
            else:
                repeat_streak = 1
                last_text_norm = tnorm
            is_repetition = repeat_streak >= 2 and not is_build_hallu

            # Update song-gap state based on segment type
            if is_music_marker or is_repetition:
                in_song_gap = True          # still hearing music
            elif is_pure_artifact:
                in_song_gap = False         # silence artifact: may be at speech boundary
            elif _has_cyrillic(text):
                in_song_gap = False         # real Russian speech: definitely past the song

            # Track last real content end (for MUSIC block start precision)
            if _has_cyrillic(text) and not is_build_hallu and not is_repetition and not in_song_gap:
                clean_prev_end = end

            # Skip for speech_start if: hallu, repetition, OR in song territory with no Cyrillic
            skip_for_ts = is_build_hallu or is_repetition or (in_song_gap and not _has_cyrillic(text))
            if not skip_for_ts and speech_start is None:
                speech_start = start

            speech_lines.append(f"[{fmt_time(start)}] {text}")

        prev_end = end

    flush()
    return "\n\n".join(parts)


SYSTEM = """\
Ты редактор стенограмм радиопередачи «Весь этот блюз» о блюзовой музыке.
Ведущий — Андрей Евдокимов — говорит по-русски, между речью звучают блюзовые песни.

Формат входных данных:
• [T:MM:SS] — маркер начала речевого блока (одна строка)
• [MM:SS] текст — отдельные фразы внутри блока с временными метками
• [MUSIC: MM:SS–MM:SS] — музыкальный фрагмент (одна строка)

Задача:
1. Маркеры [T:MM:SS] — СОХРАНИ точно как есть, каждый на отдельной строке перед абзацем.
2. Маркеры [MUSIC: MM:SS–MM:SS] — СОХРАНИ точно как есть, каждый на отдельной строке.
3. Временные метки [MM:SS] внутри текста — УБЕРИ, они больше не нужны.
4. Исправь ошибки ASR: границы слов, опечатки, ё/е, имена исполнителей и альбомов.
   Минимальные правки: меняй только то, что явно нарушает читаемость.
   Если фраза читается нормально — оставь как есть. Не перефразируй, не переставляй слова.
5. Имена музыкантов пиши латиницей в именительном падеже без изменений.
   А) Без предлога: «записал Muddy Waters», «альбом Guy Davis», «играл Willie Dixon».
   Б) С предлогом (предлог задаёт падеж): «о Muddy Waters», «вместе с Phil Wiggins».
   Если грамматически неудобно — вставь описательный оборот: «блюзмена Muddy Waters».
   Крайний вариант — окончание через дефис: «Samuel James-ом».
   Никогда не используй апостроф для кириллических окончаний.
   Названия песен и альбомов — латиницей в кавычках: «Hoochie Coochie Man».
6. Удаляй ТОЛЬКО явные галлюцинации Whisper. Признаки галлюцинации:
   - фраза «Субтитры сделал DimaTorzok» и похожие — DimaTorzok не существует, это
     артефакт Whisper, автоматически вставляемый вместо тишины или музыки
   - любые строки субтитров («Subtitles by», «Перевод сделал» и т.п.)
   - многократные повторения одной фразы подряд
   - бессвязный набор слов без смысла
   НЕЛЬЗЯ удалять: маркер [T:MM:SS], связную русскую речь (даже короткую),
   имена исполнителей, названия песен и альбомов.
   НЕЛЬЗЯ удалять весь блок [T:...] — если в нём есть реальная речь, сохрани её.
7. Раздели речь на абзацы по смыслу внутри каждого блока [T:...].

Пример ввода:
[T:00:28]
[00:28] Satisfied, Гай Дэвис.
[04:44] Песня из альбома 2013 года.
[05:10] Вилли Диксона он записал ещё в молодости.
[05:30] Вместе с Филом Уиггинсом они записали альбом.

[MUSIC: 06:02–07:14]

[T:07:14]
[07:14] Loneliest Road That I Know, Гай Дэвис.

Пример вывода:
[T:00:28]
«Satisfied», Guy Davis. Песня из его альбома 2013 года.
Вилли Диксона он записал ещё в молодости.
Вместе с Phil Wiggins они записали альбом.

[MUSIC: 06:02–07:14]

[T:07:14]
«Loneliest Road That I Know», Guy Davis.

Выводи ТОЛЬКО отформатированный текст, без пояснений.\
"""


T_RE = re.compile(r'^\[T:([0-9:]+)\]$')
M_RE = re.compile(r'^\[MUSIC:\s*([0-9:]+)–([0-9:]+)\]$')
INLINE_TS_RE = re.compile(r'\[\d+:\d+(?::\d+)?\]\s*')


def _parse_blocks(text: str, strip_inline_ts: bool = False) -> list[tuple]:
    """Parse annotated or Claude-output text into typed block tuples.

    Returns: [('t', time_str, content), ('m', start_str, end_str), ...]
    Empty speech blocks are excluded.
    """
    lines = text.split('\n')
    blocks: list[tuple] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        mt = T_RE.match(line)
        mm = M_RE.match(line)
        if mt:
            t_start = mt.group(1)
            content_lines, i = [], i + 1
            while i < len(lines):
                if T_RE.match(lines[i].strip()) or M_RE.match(lines[i].strip()):
                    break
                content_lines.append(lines[i])
                i += 1
            content = '\n'.join(content_lines).strip()
            if strip_inline_ts:
                content = INLINE_TS_RE.sub('', content).strip()
            if content:
                blocks.append(('t', t_start, content))
        elif mm:
            blocks.append(('m', mm.group(1), mm.group(2)))
            i += 1
        else:
            i += 1
    return blocks


def add_anchors(text: str) -> str:
    """Convert [T:MM:SS] and [MUSIC: A–B] markers to <a id="..."> anchors.

    [T:MM:SS]    → <a id="tNNN"></a>  (NNN = total seconds, anchor before paragraph)
    [MUSIC: A–B] → <a id="mNNN"></a>\n\n**[MUSIC: A – B]**
    """
    def repl_t(m):
        return f'<a id="t{time_to_secs(m.group(1))}"></a>'

    def repl_m(m):
        t1, t2 = m.group(1), m.group(2)
        return f'<a id="m{time_to_secs(t1)}"></a>\n\n**[MUSIC: {t1} – {t2}]**'

    text = re.sub(r'\[T:([0-9:]+)\]', repl_t, text)
    text = re.sub(r'\[MUSIC:\s*([0-9:]+)–([0-9:]+)\]', repl_m, text)
    return text


def slug_to_meta(slug: str) -> dict:
    m = re.match(r"atb-(\d{4})-(\d{2})-(\d{2})-(.*?)(?:-part-\d+)?$", slug)
    if m:
        y, mo, d, rest = m.groups()
        artist = re.sub(r"-+", " ", rest).title()
        return {"title": f"Весь этот блюз — {artist}", "date": f"{d}.{mo}.{y}"}
    return {"title": slug, "date": ""}


def call_claude(annotated: str, system: str = SYSTEM) -> str:
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=system,
        messages=[{"role": "user", "content": annotated}],
    )
    return msg.content[0].text.strip()


# Known Whisper hallucination phrases that contain Cyrillic but are NOT real speech
_HALLUCINATION_RE = re.compile(
    r'субтитры|dimaTorzok|torzok|переводчик|продолжение следует|Продолжение следует',
    re.IGNORECASE
)

def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r'[а-яёА-ЯЁ]', text))


def _is_real_speech(text: str) -> bool:
    """Return True if deleted speech block is substantial real Russian (don't merge music around it).

    A block is NOT real speech if:
    - No Cyrillic at all (song lyrics / Latin), OR
    - Contains only known Whisper hallucination patterns (Субтитры сделал DimaTorzok etc.), OR
    - Very short Cyrillic content after stripping hallucinations (< 40 chars = brief label/name)
    """
    if not _has_cyrillic(text):
        return False
    cleaned = _HALLUCINATION_RE.sub('', text).strip()
    # If removing hallucination phrases leaves little/no Cyrillic, it was just a hallucination
    cyrillic_remaining = re.findall(r'[а-яёА-ЯЁ]+', cleaned)
    cyrillic_chars = sum(len(w) for w in cyrillic_remaining)
    return cyrillic_chars >= 40


def process_segments(slug: str, segments: list, system: str = SYSTEM) -> str:
    duration = fmt_time(segments[-1]["end"])
    meta = slug_to_meta(slug)

    annotated = build_annotated(segments)
    raw_body = call_claude(annotated, system=system)

    # Music block boundaries come from the JSON-derived annotated input (always accurate).
    # Claude's output provides cleaned speech text. Music markers in Claude's output are ignored.
    #
    # Merging logic for music blocks:
    # - If Claude deleted a speech block that was Latin-only (Whisper detecting song as speech):
    #   merge the surrounding music blocks into one (song boundary stays correct).
    # - If Claude deleted a speech block that contained Cyrillic (real host speech):
    #   keep surrounding music blocks SEPARATE (timing would drift otherwise).
    orig_blocks = _parse_blocks(annotated, strip_inline_ts=True)
    claude_speech = {b[1]: b[2] for b in _parse_blocks(raw_body) if b[0] == 't'}

    parts: list[str] = []
    pending_music: tuple[str, str] | None = None  # (start_str, end_str) accumulated

    for b in orig_blocks:
        if b[0] == 't':
            text = claude_speech.get(b[1], '').strip()
            if text:
                # Kept speech — flush any pending music, then add speech
                if pending_music:
                    parts.append(f"[MUSIC: {pending_music[0]}–{pending_music[1]}]")
                    pending_music = None
                parts.append(f"[T:{b[1]}]\n{text}")
            else:
                # Deleted speech — decide whether to merge surrounding music
                if _is_real_speech(b[2]):
                    # Was substantial real Russian speech: flush pending music as separate block
                    if pending_music:
                        parts.append(f"[MUSIC: {pending_music[0]}–{pending_music[1]}]")
                        pending_music = None
                # Else Latin/empty/hallucination: leave pending_music open for merging
        else:  # music block
            start, end = b[1], b[2]
            if pending_music:
                pending_music = (pending_music[0], end)  # extend
            else:
                pending_music = (start, end)

    if pending_music:
        parts.append(f"[MUSIC: {pending_music[0]}–{pending_music[1]}]")

    body = add_anchors('\n\n'.join(parts))
    header = f"# {meta['title']}\n\n*{meta['date']} · {duration}*\n\n---\n\n"
    return header + body


def resolve(arg: str) -> str:
    p = Path(arg)
    return p.stem if p.suffix else arg


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY not set")

    args = sys.argv[1:]
    prompt_file = None
    out_dir = None
    force = False
    slugs_raw = []

    i = 0
    while i < len(args):
        if args[i] == "--prompt" and i + 1 < len(args):
            prompt_file = args[i + 1]; i += 2
        elif args[i] == "--out-dir" and i + 1 < len(args):
            out_dir = Path(args[i + 1]); i += 2
        elif args[i] == "--force":
            force = True; i += 1
        else:
            slugs_raw.append(args[i]); i += 1

    slugs = [resolve(a) for a in slugs_raw]
    if not slugs:
        print(__doc__)
        sys.exit(1)

    system = SYSTEM
    if prompt_file:
        system = Path(prompt_file).read_text(encoding="utf-8").strip()
        print(f"Using prompt: {prompt_file}")

    md_dir = out_dir or TRANSCRIPT_MD_DIR
    md_dir.mkdir(parents=True, exist_ok=True)

    for slug in slugs:
        json_path = TRANSCRIPT_DIR / f"{slug}.json"
        md_path = md_dir / f"{slug}.md"

        if not json_path.exists():
            print(f"Not found: {json_path}")
            continue
        if md_path.exists() and not force:
            print(f"Skip (exists): {md_path}  (use --force to re-run)")
            continue

        print(f"\n→ Post-processing: {slug}")
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        segs = data.get("segments", [])
        if not segs:
            print("  No segments — skipping")
            continue

        print(f"  {len(segs)} segments, {fmt_time(segs[-1]['end'])}, calling Claude...")
        md = process_segments(slug, segs, system=system)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md)

        print(f"  → {md_path}\n")
        print("=" * 70)
        print(md)
        print("=" * 70)


if __name__ == "__main__":
    main()
