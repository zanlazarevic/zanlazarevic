#!/usr/bin/env python3
"""Build profile-dark.svg and profile-light.svg: an ASCII portrait next to a neofetch-style card.

    python3 build/build_profile.py            # writes profile-dark.svg + profile-light.svg in the repo root
    python3 build/build_profile.py --print    # also prints the dark-theme ASCII to the terminal

Inputs : assets/photo.jpg            the portrait
         assets/photo-mask.png       optional person mask (white = person), see build/mask_person.swift
         build/stats.json            GitHub numbers, see build/fetch_stats.sh
Edit the PERSONAL block, rerun, commit the two SVGs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import pathlib
import textwrap

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
PHOTO = ROOT / "assets" / "photo.jpg"
MASK = ROOT / "assets" / "photo-mask.png"
STATS = ROOT / "build" / "stats.json"

# ── PERSONAL: edit me ────────────────────────────────────────────────────────
LOGIN = "zanlazarevic"
TAGLINE = "Don't follow me, I have no idea where I am going."
ABOUT = ("Recommended by 4 out of 5 people that recommend things. Appreciator of endurance. "
         "I also make things with code, pixels and stuff from the periodic table.")   # wrapped to the card width
BIRTHDAY = "1987-09-18"      # Uptime shows your age. None → time since you joined GitHub.
OS = "macOS, Omarchy"
HOST = "Ava · ava.ai"
KERNEL = "Co-Founder & Chief Product Officer"
SHELL = "zsh"
IDE = "Claude Code, Claude CLI"
LANGUAGES_REAL = ""          # e.g. "Slovenian, English" — empty hides the line
HOBBIES = ""                 # empty hides the line
EMAIL = "zan@ava.ai"
LINKEDIN = "in/zanlazarevic"    # empty hides the line
SHOW_LINES_OF_CODE = True    # GitHub counts every added line, lockfiles and bundles included
LANGUAGES = ["Python", "TypeScript", "JavaScript", "Rust"]   # empty list → top TOP_LANGUAGES by bytes from stats.json
TOP_LANGUAGES = 3
SKIP_LANGUAGES = {"HTML", "CSS", "SCSS", "PLpgSQL", "Jupyter Notebook", "Dockerfile", "Batchfile",
                  "Procfile", "CMake", "Makefile", "Metal", "QML", "PowerShell"}

# ── LAYOUT ───────────────────────────────────────────────────────────────────
COLS = 60            # portrait width in characters
CELL_ASPECT = 0.5    # a monospace cell is about twice as tall as it is wide
GAP = 3              # blank columns between portrait and card
CARD_W = 50          # card width in characters (values are right-aligned to it)
FONT_PX = 12         # GitHub renders code at ~12px too
LINE_H = 1.25        # em
PAD = 24             # px
RAMP = " .:-=+*#%@"  # darkest → brightest
EQUALIZE = 0.8       # 0 = keep the photo's tones, 1 = spread them evenly over the ramp (more detail)
GAMMA = 1.0          # < 1 lifts the midtones, > 1 darkens them

THEMES = {
    "dark":  dict(bg="#171A20", border="#2D323E", text="#E7E2F2", art="#C9BAEE", key="#EFDCAB",
                  head="#ADC2EF", dim="#867DA6", green="#ABDFC5", red="#EFADC0"),
    "light": dict(bg="#F7F5FB", border="#DDD6EC", text="#252932", art="#6E56B0", key="#8A6A1E",
                  head="#3B5BA9", dim="#867DA6", green="#2E7D5B", red="#B04A6A"),
}


# ── portrait ─────────────────────────────────────────────────────────────────
def portrait_levels() -> np.ndarray:
    """Return a (rows, COLS) grid of brightness levels 0..len(RAMP)-1, or -1 for background."""
    img = Image.open(PHOTO).convert("L")
    w, h = img.size
    rows = max(1, round(COLS * h / w * CELL_ASPECT))
    gray = np.asarray(img, dtype=np.float32)
    if MASK.exists():
        mask = np.asarray(Image.open(MASK).convert("L").resize((w, h)), dtype=np.float32) / 255.0
        person = (mask > 0.5) | (gray > 200)      # keep the bright overlay even where it leaves the head
    else:
        person = gray > 55                        # no mask: drop the dark background by brightness

    def shrink(arr: np.ndarray) -> np.ndarray:
        return np.asarray(Image.fromarray(arr.astype(np.float32)).resize((COLS, rows), Image.BOX))

    cover = shrink(person.astype(np.float32))
    mean_gray = shrink(np.where(person, gray, 0.0)) / np.maximum(cover, 1e-6)
    inside = cover > 0.5
    if not inside.any():
        raise SystemExit("mask covers nothing — check assets/photo-mask.png")
    vals = mean_gray[inside]
    lo, hi = np.percentile(vals, [1, 99])
    linear = np.clip((mean_gray - lo) / max(hi - lo, 1.0), 0.0, 1.0)
    ranked = np.searchsorted(np.sort(vals), mean_gray, side="right") / len(vals)   # histogram equalisation
    norm = np.clip((1 - EQUALIZE) * linear + EQUALIZE * ranked, 0.0, 1.0) ** GAMMA
    levels = np.rint(norm * (len(RAMP) - 1)).astype(int)
    levels[~inside] = -1
    return levels


def portrait_lines(levels: np.ndarray, invert: bool) -> list[str]:
    top = len(RAMP) - 1
    lines = []
    for row in levels:
        chars = []
        for lv in row:
            if lv < 0:
                chars.append(" ")
            else:
                chars.append(RAMP[top - lv] if invert else RAMP[lv])
        lines.append("".join(chars))
    return lines


# ── card ─────────────────────────────────────────────────────────────────────
Span = tuple[str, str]  # (text, css class)


def kv(key: str, value: list[Span]) -> list[Span]:
    vlen = sum(len(t) for t, _ in value)
    dots = max(2, CARD_W - len(key) - 3 - vlen)
    return [(key + ":", "k"), (" " + "." * dots + " ", "d"), *value]


def section(title: str) -> list[Span]:
    return [("— " + title + " ", "h"), ("─" * max(2, CARD_W - len(title) - 3), "d")]


def age_text(start: dt.date, today: dt.date) -> str:
    years, months, days = today.year - start.year, today.month - start.month, today.day - start.day
    if days < 0:
        months -= 1
        prev_month_end = today.replace(day=1) - dt.timedelta(days=1)
        days += prev_month_end.day
    if months < 0:
        years -= 1
        months += 12
    parts = [(years, "year"), (months, "month"), (days, "day")]
    return ", ".join(f"{n} {unit}{'' if n == 1 else 's'}" for n, unit in parts if n or unit == "day")


def compact(n: int) -> str:
    for div, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "k")):
        if n >= div:
            return f"{n / div:.2f}{suffix}".replace(".00", "")
    return f"{n:,}"


def card_lines(stats: dict, today: dt.date) -> list[list[Span]]:
    start = dt.date.fromisoformat(BIRTHDAY) if BIRTHDAY else dt.date.fromisoformat(stats["created_at"][:10])
    langs = sorted(((v, k) for k, v in stats["languages"].items() if k not in SKIP_LANGUAGES), reverse=True)
    lang_text = ", ".join(LANGUAGES) if LANGUAGES else ", ".join(k for _, k in langs[:TOP_LANGUAGES])

    lines: list[list[Span]] = [
        [(f"{LOGIN}@github ", "h"), ("─" * max(2, CARD_W - len(LOGIN) - 8), "d")],
        [(TAGLINE, "t")] if TAGLINE else [],
        *([[]] + [[(line, "")] for line in textwrap.wrap(ABOUT, CARD_W)] if ABOUT else []),
        [],
        kv("OS", [(OS, "")]),
        kv("Uptime", [(age_text(start, today), "")]),
        kv("Host", [(HOST, "")]),
        kv("Kernel", [(KERNEL, "")]),
        kv("Shell", [(SHELL, "")]),
        kv("IDE", [(IDE, "")]),
        kv("Languages", [(lang_text, "")]),
    ]
    if LANGUAGES_REAL:
        lines.append(kv("Languages.Real", [(LANGUAGES_REAL, "")]))
    if HOBBIES:
        lines.append(kv("Hobbies", [(HOBBIES, "")]))
    lines += [[], section("Contact"), kv("Email", [(EMAIL, "")])]
    if LINKEDIN:
        lines.append(kv("LinkedIn", [(LINKEDIN, "")]))
    lines += [
        [],
        section("GitHub Stats"),
        kv("Repos", [(f"{stats['repos_contributed']:,}", "")]),
        kv("Commits", [(f"{stats['commits']:,}", "")]),
        kv("Pull Requests", [(f"{stats['pull_requests']:,}", "")]),
        kv("Followers", [(f"{stats['followers']:,}", "")]),
    ]
    if SHOW_LINES_OF_CODE:
        net = stats["additions"] - stats["deletions"]
        lines.append(kv("Lines of Code", [(compact(net), ""), (" (", "d"), (compact(stats["additions"]) + "++", "g"),
                                          (", ", "d"), (compact(stats["deletions"]) + "--", "r"), (")", "d")]))
    return lines


# ── svg ──────────────────────────────────────────────────────────────────────
def esc(s: str) -> str:
    return html.escape(s, quote=False)


def build_svg(theme: str, art: list[str], card: list[list[Span]]) -> str:
    t = THEMES[theme]
    n = max(len(art), len(card))
    lh = FONT_PX * LINE_H
    width = round(PAD * 2 + (COLS + GAP + CARD_W) * FONT_PX * 0.61)   # 0.61em ≈ Menlo/SF Mono advance + slack
    height = round(PAD * 2 + n * lh)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{esc(LOGIN)} — ASCII portrait and profile card">',
        "<style>"
        f"text{{font-family:ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;"
        f"font-size:{FONT_PX}px;white-space:pre;fill:{t['text']}}}"
        f".a{{fill:{t['art']}}}.k{{fill:{t['key']}}}.h{{fill:{t['head']};font-weight:600}}.d{{fill:{t['dim']}}}"
        f".g{{fill:{t['green']}}}.r{{fill:{t['red']}}}.t{{fill:{t['dim']};font-style:italic}}"
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>',
    ]
    for i in range(n):
        y = PAD + FONT_PX + i * lh
        row = art[i] if i < len(art) else ""
        spans = [f'<tspan class="a">{esc(row.ljust(COLS))}</tspan>', " " * GAP]
        for text, cls in (card[i] if i < len(card) else []):
            spans.append(f'<tspan class="{cls}">{esc(text)}</tspan>' if cls else esc(text))
        out.append(f'<text x="{PAD}" y="{y:.2f}" xml:space="preserve">{"".join(spans)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", help="print the dark-theme ASCII portrait")
    args = ap.parse_args()

    stats = json.loads(STATS.read_text(encoding="utf-8"))
    today = dt.date.today()
    levels = portrait_levels()
    card = card_lines(stats, today)
    for theme, invert in (("dark", False), ("light", True)):
        art = portrait_lines(levels, invert)
        (ROOT / f"profile-{theme}.svg").write_text(build_svg(theme, art, card), encoding="utf-8")
    if args.print:
        for art_row, card_row in zip(portrait_lines(levels, False), card + [[]] * len(levels)):
            print(art_row + " " * GAP + "".join(t for t, _ in card_row))
    print(f"wrote profile-dark.svg + profile-light.svg  ({levels.shape[1]}x{levels.shape[0]} portrait)")


if __name__ == "__main__":
    main()
