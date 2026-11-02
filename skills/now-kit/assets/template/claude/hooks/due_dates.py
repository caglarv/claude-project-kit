#!/usr/bin/env python3
"""SessionStart helper — highlights due tasks in the NOW.md "## Scheduled" section.
Line format: `- YYYY-MM-DD: task`. Due: date <= today.
Doesn't depend on Claude remembering. Always exits 0.
"""
import datetime
import re
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "NOW.md"
today = datetime.date.today()
try:
    lines = open(p, encoding="utf-8").read().splitlines()
except OSError:
    lines = []

sec, due, bad = False, [], []
for l in lines:
    if l.startswith("## "):
        sec = l[3:].strip() == "Scheduled"
        continue
    if not sec:
        continue
    m = re.match(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\s*:?\s*(.+)", l)
    if not m:
        continue
    try:
        dt = datetime.date.fromisoformat(m.group(1))
    except ValueError:
        bad.append(l.strip())
        continue
    if dt <= today:
        due.append((dt, m.group(2).strip()))

if bad:
    print(f"⚠ Scheduled lines with an invalid date ({len(bad)}) — fix them in NOW.md:")
    for l in bad:
        print(f"   {l}")
if due:
    print(f"⏰ DUE TASKS ({len(due)}) — handle today, don't postpone; remove from NOW.md Scheduled when done:")
    for dt, t in sorted(due):
        print(f"   [{dt}] {t}")
