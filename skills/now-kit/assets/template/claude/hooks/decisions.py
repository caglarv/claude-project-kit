#!/usr/bin/env python3
"""decisions.py — keeps NOW.md decisions in one list that is never trimmed: evidence/DECISIONS.md.

Why: NOW.md "Dead ends" holds ≤5 items; at every close-out the oldest one drops out and survives only in the archive.
This script appends those items (and any "Decision:" line in any section) to DECISIONS.md once.
It never deletes, rewrites or summarises; existing lines are left as they are, new ones go at the end.

  python3 .claude/hooks/decisions.py collect   append new items from NOW.md (close.py archive calls this itself)
  python3 .claude/hooks/decisions.py backfill  scan evidence/now_archive/*.md + NOW.md, oldest first (run once)
Options: --now PATH · --archive DIR · --out PATH (defaults are relative to the project root).
An item is not added twice: an exact copy, or one sharing ≥60% of its word stems with an earlier item (the same
decision reworded at a later close-out), is skipped; the first date and wording stay. Text passes secret_filter.
Idea from avenoxbeyin beyin_v3_compact.py "Kararlar.md" (MIT, Avenox 2026); code written anew for this kit.
Exit code: 0 (also when NOW.md is missing — it never stops a close-out) · 2 only for a wrong command.
"""
import argparse
import glob
import os
import re
import sys
import unicodedata

H = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(H, "..", ".."))
sys.dont_write_bytecode = True  # no __pycache__ inside .claude/hooks
sys.path.insert(0, H)
try:
    from secret_filter import scrub
except Exception:
    def scrub(text: str) -> str:
        return text

SECTION = "## Dead ends"
DECISION_LINE = re.compile(r"(?i)^\s*(?:[-*]\s*)?\**decision\**\s*(?:\([^)]*\))?\s*\**\s*:")
DATE_HEADER = re.compile(r"^#\s*NOW\b.*?(20\d\d-\d\d-\d\d)")
DATE_FILE = re.compile(r"(20\d\d-\d\d-\d\d)")
HEADER = ("# DECISIONS — a list that is never trimmed\n\n"
          "NOW.md \"Dead ends\" items and \"Decision:\" lines; `.claude/hooks/decisions.py` appends them.\n"
          "Lines are never deleted; a decision that no longer holds gets `~~struck through~~` + the new decision on its own line.\n"
          "Not loaded on start; grep it.\n\n")
LINE = re.compile(r"^- (20\d\d-\d\d-\d\d|\?) · (.+)$")


def key(text: str) -> str:
    """For exact-duplicate checks: NFC, case, whitespace and strike-through marks don't matter."""
    m = unicodedata.normalize("NFC", text).casefold().replace("~~", "")
    return " ".join(m.split()).strip(" .;")


def stems(text: str) -> set:
    """Rough stems for similarity: ASCII-folded words of ≥3 letters, first 5 letters each."""
    m = unicodedata.normalize("NFKD", key(text)).encode("ascii", "ignore").decode()
    return {w[:5] for w in re.findall(r"[a-z]{3,}", m)}


def same_decision(new: set, earlier) -> bool:
    """The same decision is reworded at each close-out; ≥60% of the shorter one's stems shared = the same."""
    if len(new) < 4:
        return False
    for e in earlier:
        if len(e) >= 4 and len(new & e) / min(len(new), len(e)) >= 0.6:
            return True
    return False


def items(path: str):
    """(date, [item]) from a NOW-format file. (None, []) if unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return None, []
    date = None
    if lines:
        t = DATE_HEADER.search(lines[0])
        date = t.group(1) if t else None
    if not date:
        t = DATE_FILE.search(os.path.basename(path))
        date = t.group(1) if t else None
    out, inside = [], False
    for s in lines:
        if s.startswith("## "):
            inside = s.strip() == SECTION
            continue
        text = None
        if inside and re.match(r"^\s*[-*]\s+\S", s):
            text = re.sub(r"^\s*[-*]\s+", "", s)
        elif DECISION_LINE.match(s):
            text = re.sub(r"^\s*[-*]\s+", "", s)
        if text and key(text) not in ("", "none", "(none)", "—", "-"):
            out.append(" ".join(text.split()))
    return date, out


def existing(out: str):
    keys, sets = set(), []
    try:
        with open(out, encoding="utf-8") as f:
            for s in f:
                m = LINE.match(s.rstrip("\n"))
                if m:
                    keys.add(key(m.group(2)))
                    sets.append(stems(m.group(2)))
    except OSError:
        pass
    return keys, sets


def inside_root(path: str) -> bool:
    real_root = os.path.realpath(ROOT)
    d = os.path.realpath(os.path.dirname(path))
    return (d == real_root or d.startswith(real_root + os.sep)) and not os.path.islink(path)


def append(sources, out: str) -> int:
    keys, sets = existing(out)
    new = []
    for path in sources:
        date, found = items(path)
        for item in found:
            item = scrub(item)
            k, st = key(item), stems(item)
            if k in keys or same_decision(st, sets):
                continue
            keys.add(k)
            sets.append(st)
            new.append(f"- {date or '?'} · {item}")
    if not new:
        return 0
    if not inside_root(out):
        raise OSError("output is a symlink or leads outside the project")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    old = ""
    if os.path.exists(out):
        with open(out, encoding="utf-8") as f:
            old = f.read()
    if not old.strip():
        old = HEADER
    elif not old.endswith("\n"):
        old += "\n"
    tmp = f"{out}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(old + "\n".join(new) + "\n")
    os.replace(tmp, out)  # if interrupted, the old file stays intact
    return len(new)


def default_out(now: str) -> str:
    ev = os.path.join(ROOT, "evidence")
    return os.path.join(ev if os.path.isdir(ev) else os.path.dirname(now), "DECISIONS.md")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Append NOW.md decisions to evidence/DECISIONS.md")
    ap.add_argument("step", choices=["collect", "backfill"])
    ap.add_argument("--now", default=os.path.join(ROOT, os.environ.get("CLOSE_NOW") or "NOW.md"))  # empty = NOW.md
    ap.add_argument("--archive")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    out = a.out or default_out(a.now)
    archive = a.archive or os.path.join(ROOT, "evidence", "now_archive")
    if a.step == "collect":
        sources = [a.now]
    else:
        def order(path):  # by the date in the file name, oldest first; no date → by name, last
            t = DATE_FILE.search(os.path.basename(path))
            return (t.group(1) if t else "9999", os.path.basename(path))
        sources = sorted(glob.glob(os.path.join(archive, "*.md")), key=order) + [a.now]
    if not any(os.path.isfile(s) for s in sources):
        print("decisions: no NOW.md found — skipped")
        return 0
    n = append(sources, out)
    rel = os.path.relpath(out, ROOT)
    print(f"decisions: {n} new item(s) → {rel}" if n else f"decisions: nothing new ({rel})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # never stop a close-out
        print(f"decisions: skipped ({type(exc).__name__}: {exc})")
        sys.exit(0)
