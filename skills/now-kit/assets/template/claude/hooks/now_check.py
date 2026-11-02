#!/usr/bin/env python3
"""NOW.md checker (RULES.md §1 template).

Checks: ≤40 lines · header line `# NOW · YYYY-MM-DD · commit <7 hex | none>` ·
8 required `## ` sections · per-section `- ` item limits · Scheduled line format
`- YYYY-MM-DD: task` with a real date · exactly the 8 headings, no duplicates, no extra sections ·
items written as `- ` (other list markers are refused, so the limits can't be dodged) · forbidden phrases · "stale" warning if the date is >14 days old.

Output / exit code:
  0  `OK <N>`            (warnings as `OK <N> warn:...`, still 0)
  1  `BROKEN <N> [lines>40] [header:...] [missing:...] [limit:...] [scheduled:...] [forbidden:...]`
  2  `ERROR <message>`   (internal error — file unreadable etc.; NOT reported as BROKEN)
"""
import datetime
import re
import sys

SECTIONS = [  # (heading, item limit)
    ("Active task", 2), ("Next ONE step", 3), ("Pending", 6), ("Scheduled", 2),
    ("Background debt", 3), ("Dead ends", 5), ("MISTAKES I MADE", 5),
    ("Saved to memory", 1),
]
FORBIDDEN = ["LATEST", "THIS BLOCK IS VALID", "(old:"]
HEADER_RE = re.compile(r"^# NOW · (\d{4}-\d{2}-\d{2}) · commit ([0-9a-f]{7,}|none)\b")
SCHEDULE_RE = re.compile(r"^- \d{4}-\d{2}-\d{2}: \S")
OTHER_LIST_RE = re.compile(r"^\s*([*+]|\d+[.)])\s|^\s+-\s")  # also indented "- ", which the limits wouldn't count
MAX_LINES = 40
STALE_DAYS = 14


def valid_date(s: str) -> bool:
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def main() -> int:
    p = sys.argv[1] if len(sys.argv) > 1 else "NOW.md"
    try:
        lines = open(p, encoding="utf-8").read().splitlines()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR unreadable: {exc}")
        return 2

    n = len(lines)
    problems, warnings = [], []
    if n > MAX_LINES:
        problems.append(f"lines>{MAX_LINES}")

    m = HEADER_RE.match(lines[0]) if lines else None
    if not m:
        problems.append("header:'# NOW · YYYY-MM-DD · commit <hash>' expected")
    else:
        try:
            date = datetime.date.fromisoformat(m.group(1))
            age = (datetime.date.today() - date).days
            if age > STALE_DAYS:
                warnings.append(f"stale:{age}days")
        except ValueError:
            problems.append("header:invalid date")

    # split into sections
    section, body, duplicate = None, {}, []
    for l in lines:
        if l.startswith("## "):
            section = l[3:].strip()
            if section in body:
                duplicate.append(section)
            body.setdefault(section, [])
        elif section is not None:
            body[section].append(l)

    def find(name):
        return name if name in body else None

    if duplicate:
        problems.append("duplicate:" + ",".join(duplicate))
    allowed = {name for name, _ in SECTIONS}
    extra = [b for b in body if b not in allowed]
    if extra:
        problems.append("extra:" + ",".join(extra))
    other_markers = [l for b in body.values() for l in b if OTHER_LIST_RE.match(l)]
    if other_markers:
        problems.append(f"bullets:{len(other_markers)} lines use '*', '+', numbers or indentation — write items as '- '")

    missing = [name for name, _ in SECTIONS if find(name) is None]
    if missing:
        problems.append("missing:" + ",".join(missing))
    for name, lim in SECTIONS:
        b = find(name)
        if b is None:
            continue
        items = [l for l in body[b] if l.startswith("- ")]
        if len(items) > lim:
            problems.append(f"limit:{name}={len(items)}>{lim}")
        if name == "Scheduled":
            bad = [l for l in items if not SCHEDULE_RE.match(l) or not valid_date(l[2:12])]
            if bad:
                problems.append(f"scheduled:{len(bad)} lines not '- YYYY-MM-DD: task'")

    forbidden = [k for k in FORBIDDEN if any(k in l for l in lines)]
    if forbidden:
        problems.append("forbidden:" + ",".join(forbidden))

    if problems:
        print(f"BROKEN {n} " + " ".join(problems))
        return 1
    print(f"OK {n}" + (" warn:" + ",".join(warnings) if warnings else ""))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR {exc}")
        sys.exit(2)
