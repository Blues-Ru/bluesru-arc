#!/usr/bin/env python3
"""
Estimate broadcast dates of undated ATB shows from their transcripts.

Unit of work is a *series*: all files sharing a slug apart from a trailing -part-N.
Old tape-sourced files are cassette sides (~23 min), so a show can span sides and a
side can hold the end of one show and the start of the next; the model segments the
series into broadcasts before dating them. A single-file episode is a one-side series.

Stage 1 (Claude API, per series): find show boundaries, extract every dated clue —
anniversaries ("80 лет Джону Ли Хукеру"), new releases, recent deaths, upcoming
concerts, seasons/holidays — and resolve each to a [earliest, latest] window,
verifying birth/death/release dates with web search.

Stage 2 (deterministic): combine windows. Each clue votes for its window
(weight by confidence); the best-supported date is found, and the final range
is the intersection of the clues that agree with it. Disagreeing clues are
reported as conflicts rather than dropped silently.

Input:  extracted-data/atb/transcripts/{slug}.json   (from transcribe_atb.py)
Output: extracted-data/atb/dating/{series}.json      (shows, clues, per-show estimates)

Usage:
    python3 date_atb.py SLUG|GLOB [...] [--prior 1991-01-01:1996-12-31] [--force]
    python3 date_atb.py 'atb-199x-*' --prior 1991-01-01:1996-12-31
    python3 date_atb.py --combine-only 'atb-199x-*'      # re-run stage 2 only

Requires: ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import anthropic

from postprocess_atb import _HALLUCINATION_RE, _MUSIC_MARKER_RE

ARC = Path(__file__).resolve().parent.parent.parent
WORKSPACE = ARC.parent
TRANSCRIPTS_DIR = WORKSPACE / "extracted-data/atb/transcripts"
OUT_DIR = WORKSPACE / "extracted-data/atb/dating"
MODEL = "claude-opus-5-5"
WEIGHT = {"high": 3, "medium": 2, "low": 1}

CLUE_KINDS = [
    "anniversary",      # "N лет со дня рождения/смерти X", jubilee of a record/label/festival
    "age_now",          # "X сейчас 70 лет", "в свои 80"
    "recent_death",     # "недавно ушёл из жизни", "памяти X"
    "alive",            # X spoken of as living / still touring (upper bound = death date)
    "new_release",      # "новый альбом", "только что вышел", "свежий диск"
    "past_release",     # album/compilation mentioned as existing (lower bound = release date)
    "event",            # concerts, tours, festivals, awards — upcoming or just happened
    "season_holiday",   # New Year, Christmas, summer, "к 8 марта"
    "broadcast_meta",   # station names, frequencies, schedules, other shows referenced
    "other",
]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["shows", "clues", "notes"],
    "properties": {
        "shows": {
            "type": "array",
            "description": "distinct broadcasts in this series, in order",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["show", "start_side", "start_t", "end_side", "end_t", "title", "boundary_evidence"],
                "properties": {
                    "show": {"type": "integer", "description": "1-based"},
                    "start_side": {"type": "integer"},
                    "start_t": {"type": "number"},
                    "end_side": {"type": "integer"},
                    "end_t": {"type": "number"},
                    "title": {"type": "string", "description": "main topic, e.g. 'B.B. King — 70th birthday'"},
                    "boundary_evidence": {"type": "string", "description": "intro/outro phrases or topic change that mark the edges; say 'starts/ends mid-show' if cut by the tape"},
                },
            },
        },
        "clues": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["show", "side", "kind", "t", "quote", "subject", "fact", "earliest", "latest",
                             "reasoning", "confidence"],
                "properties": {
                    "show": {"type": "integer"},
                    "side": {"type": "integer"},
                    "kind": {"type": "string", "enum": CLUE_KINDS},
                    "t": {"type": "number", "description": "seconds into that side, from the [side|m:ss] marker"},
                    "quote": {"type": "string", "description": "verbatim transcript excerpt (Russian)"},
                    "subject": {"type": "string", "description": "artist / album / event in canonical spelling"},
                    "fact": {"type": "string", "description": "the real-world dated fact relied on, e.g. 'John Lee Hooker born 1917-08-22'"},
                    "earliest": {"type": "string", "description": "YYYY-MM-DD, earliest possible broadcast date implied by this clue alone"},
                    "latest": {"type": "string", "description": "YYYY-MM-DD, latest possible broadcast date implied by this clue alone"},
                    "reasoning": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
        "notes": {"type": "string", "description": "anything else useful for dating, incl. ASR doubts"},
    },
}

SYSTEM = """You are a music historian dating an undated episode of "Весь этот блюз" (All That Blues), \
a Russian blues radio show hosted by Andrey Evdokimov. You get Whisper transcripts of one or more \
consecutive "sides" with [side|m:ss] markers. They contain ASR errors, especially in English names, \
album titles and numbers — reconstruct the intended names, and when a number is doubtful say so in \
reasoning and lower confidence. Music passages have been removed, so gaps in time are songs.

Sides may be cassette sides recorded off the air: a broadcast can continue from one side to the next, \
and one side can contain the end of one broadcast and the start of another. First segment the series \
into distinct broadcasts using intros ("Вы слушаете программу «Весь этот блюз»", "ведёт Андрей \
Евдокимов"), outros ("до встречи через неделю"), greetings and clear topic changes. Do not split one \
broadcast just because the side changes. Then assign every clue to its broadcast.

Find every statement that constrains WHEN the show was broadcast, and turn each into a date window \
[earliest, latest] that follows from that clue ALONE. Use web search to verify birth/death dates, \
release dates and event dates whenever you are not certain; prefer authoritative discographies.

Window conventions (adjust when the wording is more specific):
- Anniversary "N лет со дня рождения X" / "X исполнилось N" / jubilee: the anniversary date in year \
birth+N, window from ~3 weeks before to ~5 weeks after (hosts mark jubilees in the nearest show). \
"Сегодня"/"на этой неделе" → a few days either side. "В этом году" → that whole calendar year.
- Age stated as current ("ему сейчас 70"): the year between the 70th and 71st birthday.
- New release ("новый", "только что вышел", "свежий"): [release date, release + 12 months].
- Existing release or past event mentioned: lower bound only → latest = "9999-12-31".
- Recent death ("недавно умер", "памяти"): [death date, death + 3 months]. Person mentioned as \
deceased: lower bound = death date. Person spoken of as alive or touring: upper bound = death date \
(earliest = "0001-01-01").
- Upcoming concert/tour: [announcement plausibility ~2 months before, event date].
- Season/holiday: the obvious window for the relevant year range.

Do not use any prior range you are given to pick between candidate facts — state each clue's window \
from the clue alone; the prior is only context. Skip statements that give no date information \
(generic biography of long-dead artists with no anniversary framing). Quote verbatim, give side and t \
in seconds. Relative references between broadcasts ("на прошлой неделе мы слушали…") belong in notes."""


def fmt_t(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _is_artifact(text):
    """Whisper hallucination during music: phantom subtitle credits, 'ДИНАМИЧНАЯ МУЗЫКА' etc.
    No real ATB speech mentions subtitles, so any match marks the whole segment."""
    if _HALLUCINATION_RE.search(text) or re.search(r"(?i)корректор", text):
        return True
    return not re.search(r"\w{2}", _MUSIC_MARKER_RE.sub("", text))


def series_key(slug):
    return re.sub(r"-part-\d+$", "", slug)


def side_number(slug):
    m = re.search(r"-part-(\d+)$", slug)
    return int(m[1]) if m else 1


def series_text(slugs):
    out = []
    for slug in slugs:
        side = side_number(slug)
        segs = json.loads((TRANSCRIPTS_DIR / f"{slug}.json").read_text(encoding="utf-8")).get("segments", [])
        out.append(f"=== side {side} ({slug}) ===")
        out += [f"[{side}|{fmt_t(s['start'])}] {s['text'].strip()}" for s in segs if not _is_artifact(s["text"])]
    return "\n".join(out)


def extract_clues(client, series, slugs, prior):
    user = f"Series: {series} ({len(slugs)} side(s))\n"
    if prior:
        user += f"Prior knowledge (context only): broadcast between {prior[0]} and {prior[1]}.\n"
    user += "\nTranscript:\n" + series_text(slugs)
    messages = [{"role": "user", "content": user}]
    for _ in range(5):  # web search may pause the turn; resume until done
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=SYSTEM,
            messages=messages,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 25}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            resp = stream.get_final_message()
        if resp.stop_reason == "pause_turn":
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
            continue
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"refused: {resp.stop_details}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("hit max_tokens")
        text = [b.text for b in resp.content if b.type == "text"]
        return json.loads(text[-1]), resp.usage
    raise RuntimeError("too many pause_turn rounds")


def _d(s):
    try:
        return date.fromisoformat(s)
    except ValueError:
        return date.min if s.startswith("0001") else date.max


def combine(clues, prior=None):
    """Best-supported date by weighted vote, then intersect the clues that contain it."""
    usable = [c for c in clues if _d(c["earliest"]) <= _d(c["latest"])]
    lo_p, hi_p = (date.fromisoformat(prior[0]), date.fromisoformat(prior[1])) if prior else (None, None)
    points = sorted({_d(c["earliest"]) for c in usable} | {_d(c["latest"]) for c in usable})
    points = [p for p in points if p not in (date.min, date.max)
              and (not prior or lo_p <= p <= hi_p)] or ([lo_p] if prior else [])

    def score(p):
        return sum(WEIGHT[c["confidence"]] for c in usable if _d(c["earliest"]) <= p <= _d(c["latest"]))

    if not points:
        return dict(earliest=prior[0] if prior else None, latest=prior[1] if prior else None,
                    support=[], conflicts=[], score=0)
    best = max(points, key=score)
    agree = [c for c in usable if _d(c["earliest"]) <= best <= _d(c["latest"])]
    lo = max([_d(c["earliest"]) for c in agree] + ([lo_p] if prior else []))
    hi = min([_d(c["latest"]) for c in agree] + ([hi_p] if prior else []))
    informative = [c for c in usable if _d(c["earliest"]) != date.min or _d(c["latest"]) != date.max]
    return dict(
        earliest=lo.isoformat(), latest=hi.isoformat(), days=(hi - lo).days + 1, score=score(best),
        support=[c["subject"] for c in agree if c in informative],
        conflicts=[dict(subject=c["subject"], earliest=c["earliest"], latest=c["latest"],
                        confidence=c["confidence"]) for c in informative if c not in agree],
    )


def combine_shows(rec, prior):
    for show in rec["shows"]:
        show["estimate"] = combine([c for c in rec["clues"] if c["show"] == show["show"]], prior)
    return rec


def resolve_series(patterns):
    """Map series key → its transcript slugs in side order."""
    groups = {}
    for slug in resolve_slugs(patterns):
        groups.setdefault(series_key(slug), []).append(slug)
    return {k: sorted(v, key=side_number) for k, v in groups.items()}


def resolve_slugs(patterns):
    slugs = []
    for p in patterns:
        found = sorted(f.stem for f in TRANSCRIPTS_DIR.glob(f"{p}.json"))
        if not found:
            print(f"No transcript matches: {p}", file=sys.stderr)
        slugs += found
    return list(dict.fromkeys(slugs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--prior", help="EARLIEST:LATEST bound known independently, e.g. 1991-01-01:1996-12-31")
    ap.add_argument("--force", action="store_true", help="re-run stage 1 even if output exists")
    ap.add_argument("--combine-only", action="store_true")
    args = ap.parse_args()
    prior = tuple(args.prior.split(":")) if args.prior else None
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = None if args.combine_only else anthropic.Anthropic()

    for series, slugs in resolve_series(args.patterns).items():
        out = OUT_DIR / f"{series}.json"
        rec = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        if not args.combine_only and (rec is None or args.force):
            try:
                result, usage = extract_clues(client, series, slugs, prior)
            except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as e:
                print(f"✗ {series}: {e}", file=sys.stderr)
                continue
            rec = dict(series=series, sides=slugs, model=MODEL, prior=list(prior) if prior else None, **result,
                       usage=dict(input=usage.input_tokens, output=usage.output_tokens))
        if rec is None:
            continue
        combine_shows(rec, tuple(rec["prior"]) if rec.get("prior") else prior)
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        for sh in rec["shows"]:
            e = sh["estimate"]
            print(f"{series} #{sh['show']} [{sh['start_side']}|{fmt_t(sh['start_t'])}–{sh['end_side']}|"
                  f"{fmt_t(sh['end_t'])}] {sh['title']}: {e['earliest']} … {e['latest']} ({e.get('days')} d, "
                  f"{len(e['support'])} supporting, {len(e['conflicts'])} conflicts)", flush=True)


if __name__ == "__main__":
    main()
