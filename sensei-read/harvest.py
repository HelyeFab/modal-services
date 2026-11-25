"""
Write a reading session into the vault, from what actually happened.

Every question Helye-san asked in ReadAny is one genuine stop — the selection IS the
stop. This pulls the day's exchanges out of the sensei-read service and writes:

  * $OBSIDIAN/Books/<title>/Sessions/<YYYY-MM-DD>.md   (the session record)
  * $OBSIDIAN/Books/<title>/_Book.md                   (position + session log row)

Sections with nothing real in them are DELETED, never padded — an empty heading is a
lie about what happened.

    python harvest.py [--date YYYY-MM-DD] [--book 桃太郎] [--dry-run]
"""

import argparse
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import modal

HOME = Path.home()
FLUENT = Path(os.environ.get("FLUENT_DIR", HOME / "Dev/fluent"))
OBSIDIAN = Path(os.environ.get("OBSIDIAN", HOME / "Documents/Unsync/Life-Org/04_JapaneseLanguage"))

JP = re.compile(r"[぀-ヿ㐀-鿿]")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("|", "／")).strip()


def split_turn(asked: str) -> tuple[str, str]:
    """ReadAny sends one user turn shaped as:

        关于以下文本：          <- its own localized lead-in, not content
        > <the selection>      <- blockquoted
                               <- blank
        <the question>
    """
    lines = [l.rstrip() for l in (asked or "").splitlines()]
    quoted = [l.lstrip("> ").strip() for l in lines if l.lstrip().startswith(">")]
    selection = " ".join(q for q in quoted if q).strip()

    rest = [
        l.strip() for l in lines
        if l.strip() and not l.lstrip().startswith(">") and not l.rstrip().endswith("：")
    ]
    question = rest[-1] if rest else ""

    if not selection:
        # no blockquote: fall back to the first Japanese line that is not the lead-in
        japanese = [l.strip() for l in rest if JP.search(l)]
        selection = japanese[0] if japanese else ""
        if question == selection:
            question = ""
    return selection, question


def first_lines(answer: str, limit: int = 2) -> str:
    lines = [l.strip() for l in (answer or "").splitlines() if l.strip()]
    return clean(" ".join(lines[:limit]))[:300]


def load(day: str) -> list:
    store = modal.Dict.from_name("sensei-read-sessions", create_if_missing=True)
    return store.get(f"log:{day}", [])


def read_position(book_md: Path) -> str:
    if not book_md.exists():
        return "unknown"
    m = re.search(r"^position:\s*(.+)$", book_md.read_text(encoding="utf-8"), re.M)
    return m.group(1).strip() if m else "unknown"


def build_record(title: str, day: str, rows: list, start_pos: str, minutes: int) -> tuple[str, str]:
    stops = []
    for selection, question, answer in rows:
        stops.append(f"| {clean(selection) or '—'} | {clean(question) or '—'} | {first_lines(answer)} |")

    end_pos = clean(rows[-1][0]) if rows and rows[-1][0] else start_pos

    body = [
        "---",
        "type: reading-session",
        f"book: {title}",
        f"date: {day}",
        f"from: {start_pos}",
        f"to: {end_pos}",
        f"minutes: {minutes}",
        f"asked: {len(rows)}",
        "garden_seen: []",
        f"tags: [reading, jp/companion, {title}]",
        "---",
        "",
        f"# 📖 {title} — {day}",
        "",
        f"> {start_pos} → {end_pos}",
        "",
        "<!-- Written after the fact, from the session — never from the text. -->",
        "",
        "---",
        "",
    ]

    if stops:
        body += [
            "## 🛑 Where they stopped",
            "",
            "One row per genuine stop. In ReadAny the selection **is** the stop.",
            "",
            "| Line | What blocked them | What I said |",
            "|------|-------------------|-------------|",
            *stops,
            "",
        ]
    else:
        body += ["They asked nothing this session. That is a real and good result.", ""]

    return "\n".join(body).rstrip() + "\n", end_pos


def update_book(book_md: Path, day: str, start_pos: str, end_pos: str, stops: int) -> None:
    text = book_md.read_text(encoding="utf-8")
    text = re.sub(r"^position:\s*.+$", f"position: {end_pos}", text, count=1, flags=re.M)

    row = f"| {day} | {start_pos} → {end_pos} | {stops} | [[{day}]] |"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith("| Date | From → To | Stops | Record |"):
            continue
        j = i + 2
        # Idempotent: rewrite today's row if it is already there, never append a second one.
        while j < len(lines) and lines[j].lstrip().startswith("|"):
            if lines[j].lstrip().startswith(f"| {day} "):
                lines[j] = row
                break
            if lines[j].strip() in ("| | | | |", "|  |  |  |  |"):
                lines[j] = row
                break
            j += 1
        else:
            lines.insert(j, row)
        break
    book_md.write_text("\n".join(lines) + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--book", default="桃太郎")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--catch-up", action="store_true",
                    help="harvest every logged day, not just today — for reading done "
                         "while this machine was off")
    args = ap.parse_args()

    if args.catch_up:
        store = modal.Dict.from_name("sensei-read-sessions", create_if_missing=True)
        days = store.get("days", [])
        rc = 0
        for day in days:
            args.date, args.catch_up = day, False
            rc |= harvest_day(args)
        return rc
    return harvest_day(args)


def harvest_day(args) -> int:

    raw = load(args.date)
    if not raw:
        print(f"no exchanges logged for {args.date}")
        return 0

    rows = []
    for entry in raw:
        selection, question = split_turn(entry.get("asked", ""))
        rows.append((selection, question, entry.get("answered", "")))

    stamps = [e.get("at") for e in raw if e.get("at")]
    minutes = 0
    if len(stamps) > 1:
        try:
            span = datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(stamps[0])
            minutes = max(1, round(span.total_seconds() / 60))
        except ValueError:
            minutes = 0

    book_dir = OBSIDIAN / "Books" / args.book
    book_md = book_dir / "_Book.md"
    target = book_dir / "Sessions" / f"{args.date}.md"

    # Re-running must not eat the start position: the first run already advanced
    # _Book.md, so on any later run take `from:` back out of the record we wrote.
    start_pos = ""
    if target.exists():
        m = re.search(r"^from:\s*(.+)$", target.read_text(encoding="utf-8"), re.M)
        start_pos = m.group(1).strip() if m else ""
    if not start_pos:
        start_pos = read_position(book_md)

    record, end_pos = build_record(args.book, args.date, rows, start_pos, minutes)

    print(f"book       : {args.book}")
    print(f"stops      : {len(rows)}")
    print(f"position   : {start_pos}  →  {end_pos}")
    print(f"record     : {target}")

    if args.dry_run:
        print("\n" + record)
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(record, encoding="utf-8")
    if book_md.exists():
        update_book(book_md, args.date, start_pos, end_pos, len(rows))
    print("✅ written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
