#!/usr/bin/env python3
"""close.py — the scripted steps of the close-out procedure (/close-out).

  python3 .claude/hooks/close.py archive    NOW.md → evidence/now_archive/<date>_NOW.md (a COPY, not a move,
                                            so NOW isn't lost if the session dies halfway), then decisions.py collect
                                            appends its decisions to evidence/DECISIONS.md
  python3 .claude/hooks/close.py finish     STOPS unless now_check.py says OK; reads the commit hash itself
                                            ("none" if not a git repo); overwrites resume_prompt.md; prints a one-line summary.
                                            --session <id> also writes .claude/state/closed_<id> for safety_net.py
                                            (without a valid id the session stays unmarked and gets a harmless safety note).
The other steps (writing NOW.md, RULES §6 lessons, INDEX check, tests, commit) are the assistant's.
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

import state_io  # same folder

H = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(H, "..", ".."))
NOW = os.path.join(ROOT, "NOW.md")
ARCHIVE = os.path.join(ROOT, "evidence", "now_archive")
PROMPT = os.path.join(ROOT, "resume_prompt.md")
PROJECT = {{NAME_PY}}  # filled in by setup.py as a Python string literal


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def archive() -> int:
    if not os.path.exists(NOW):
        print("no NOW.md — nothing to archive")
        return 1
    t = datetime.date.today().isoformat()
    os.makedirs(ARCHIVE, exist_ok=True)
    data = open(NOW, "rb").read()
    # "xb" refuses an existing file, so an earlier archive is never overwritten, even by a parallel call.
    for n in range(1000):
        dst = os.path.join(ARCHIVE, f"{t}_NOW.md" if n == 0 else f"{t}_{n:03d}_NOW.md")
        try:
            with open(dst, "xb") as f:
                f.write(data)
        except FileExistsError:
            continue
        shutil.copystat(NOW, dst)
        print(f"archived: {os.path.relpath(dst, ROOT)}")
        try:  # "Dead ends" + "Decision:" lines → evidence/DECISIONS.md (never trimmed); an error never stops the close-out
            sys.dont_write_bytecode = True
            sys.path.insert(0, H)
            import decisions
            decisions.main(["collect", "--now", NOW])
        except Exception as exc:  # noqa: BLE001
            print(f"decisions: skipped ({type(exc).__name__})")
        return 0
    print("could not find a free archive name")
    return 1


def finish(session: str) -> int:
    r = subprocess.run([sys.executable, os.path.join(H, "now_check.py"), NOW],
                       capture_output=True, text=True)
    result = (r.stdout or "").strip()
    if not result.startswith("OK"):
        print(f"STOPPED — NOW.md {result or r.stderr.strip() or 'could not be checked'}. Fix NOW.md first.")
        return 1
    n = result.split()[1]
    h = git("rev-parse", "--short", "HEAD") or "none"
    t = datetime.date.today().isoformat()
    with open(PROMPT, "w", encoding="utf-8") as f:
        f.write(
            f"{PROJECT} · {t} · commit {h}\n"
            "1. Read NOW.md (in Claude Code the SessionStart hook prints it automatically). READ NOTHING ELSE.\n"
            "2. START NO WORK (no code, no commands, no paid runs). First give the user a short summary from NOW.md:\n"
            "   active task, next ONE step, pending items, due scheduled items (≤12 lines, plain language). Wait for approval.\n"
            '   Once approved, do the "Next ONE step"; open other files only if that step needs them.\n'
            "3. Before writing a claim, apply the RULES.md §2 table (via grep). A summary is not a source.\n"
            '4. Before saying "new finding", run `grep -n <topic> evidence/INDEX.md`.\n'
            "5. Answers ≤12 lines, result first. Numbers/tables go into files, not the chat.\n"
            "SUMMARISE AND WAIT.\n"
        )
    marked = bool(re.fullmatch(r"[A-Za-z0-9_-]+", session)) and state_io.write(ROOT, f"closed_{session}", "")
    if not marked:
        print("note: session not marked as closed (no valid --session id) — safety_net.py will leave a note at exit")
    dirty = git("status", "--short")  # measured after writing, so resume_prompt.md itself counts
    print(f"NOW.md {n} lines · commit {h}{' · ⚠ working tree dirty' if dirty else ''} · resume_prompt.md ready")
    return 0


ap = argparse.ArgumentParser()
ap.add_argument("step", choices=["archive", "finish"])
ap.add_argument("--session", default="")
a = ap.parse_args()
sys.exit(archive() if a.step == "archive" else finish(a.session))
