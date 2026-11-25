"""
Push Helye-san's current learner state into the sensei-read endpoint.

Reads the real sources on this machine — fluent's STATE.md, the Grammar Garden via
fluent's own garden.mjs, and the book's _Book.md — and writes a compact snapshot into
the Modal Dict the endpoint reads. Re-run it whenever the state moves.

    python sync_context.py [--book 桃太郎] [--dry-run]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import modal

HOME = Path.home()
FLUENT = Path(os.environ.get("FLUENT_DIR", HOME / "Dev/fluent"))
OBSIDIAN = Path(os.environ.get("OBSIDIAN", HOME / "Documents/Unsync/Life-Org/04_JapaneseLanguage"))


def section(text: str, heading: str, stop_level: int = 2) -> str:
    """Pull one markdown section out of STATE.md by its heading."""
    lines = text.splitlines()
    out, grabbing = [], False
    for line in lines:
        if line.strip().startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line.lstrip("#").strip()
            if grabbing and level <= stop_level:
                break
            if title.startswith(heading):
                grabbing = True
                continue
        if grabbing:
            out.append(line)
    return "\n".join(out).strip()


def node_bin() -> str:
    """systemd units do not get nvm's PATH — find the newest node ourselves."""
    from shutil import which
    found = which("node")
    if found:
        return found
    candidates = sorted((HOME / ".nvm/versions/node").glob("*/bin/node"))
    return str(candidates[-1]) if candidates else "node"


def garden_due() -> list:
    try:
        raw = subprocess.run(
            [node_bin(), "scripts/garden.mjs", "status", "--json"],
            cwd=FLUENT, env={**os.environ, "OBSIDIAN": str(OBSIDIAN)},
            capture_output=True, text=True, timeout=60,
        )
        data = json.loads(raw.stdout)
    except Exception as exc:
        print(f"  garden unavailable: {exc}", file=sys.stderr)
        return []

    today = date.fromisoformat(data.get("today") or date.today().isoformat())
    due = []
    for row in data.get("reviewable", []):
        nxt = row.get("nextReview")
        if not nxt:
            continue
        try:
            overdue = (today - date.fromisoformat(nxt)).days
        except ValueError:
            continue
        if overdue >= 0:
            due.append({
                "id": row.get("id"),
                "topic": re.sub(r"\s+", " ", str(row.get("topicRaw") or "")).strip(),
                "stage": row.get("stage"),
                "overdue": overdue,
            })
    due.sort(key=lambda d: -d["overdue"])
    return due


def recent_sessions(title: str, keep: int = 3) -> list:
    """The last few session records, so a NEW thread still knows what was asked before."""
    folder = OBSIDIAN / "Books" / title / "Sessions"
    if not folder.is_dir():
        return []
    files = sorted(folder.glob("*.md"), reverse=True)[:keep]
    return [
        {"date": f.stem, "record": f.read_text(encoding="utf-8")[:2500]}
        for f in files
    ]


def book_note(title: str) -> str:
    path = OBSIDIAN / "Books" / title / "_Book.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:2000]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="桃太郎")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    state_path = FLUENT / "data/STATE.md"
    if not state_path.exists():
        print(f"❌ no STATE.md at {state_path}", file=sys.stderr)
        return 1
    state = state_path.read_text(encoding="utf-8")

    store = modal.Dict.from_name("sensei-read-context", create_if_missing=True)
    previous = store.get("context") or {}

    due = garden_due()
    if not due and previous.get("garden_due"):
        # A garden that cannot be read is not a garden with nothing due. Keep the
        # last good list rather than quietly shipping an empty one.
        print("  ⚠️  garden read failed — keeping the previous snapshot", file=sys.stderr)
        due = previous["garden_due"]

    context = {
        "generated": date.today().isoformat(),
        "learner": section(state, "Learner"),
        "position": section(state, "Current position")[:3000],
        "garden_due": due,
        "book": book_note(args.book),
        "sessions": recent_sessions(args.book),
    }

    print(f"learner block   : {len(context['learner'])} chars")
    print(f"position block  : {len(context['position'])} chars")
    print(f"garden due      : {len(context['garden_due'])} points")
    print(f"book note       : {len(context['book'])} chars")
    print(f"past sessions   : {len(context['sessions'])}")

    if args.dry_run:
        print(json.dumps(context, ensure_ascii=False, indent=2)[:1500])
        return 0

    store["context"] = context
    print("✅ pushed to sensei-read-context")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
