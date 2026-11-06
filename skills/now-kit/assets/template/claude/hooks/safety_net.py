#!/usr/bin/env python3
"""safety_net.py — SessionEnd hook. If the session ends WITHOUT /close-out, leaves a mechanical note.

It does NOT replace /close-out (no model summary, lessons or commit); it only keeps the trail:
git state + the user's last 3 messages + NOW "Next ONE step" → .claude/state/session_end_<UTC>.md (outside git).
Writes nothing only when a close-out is PROVEN for this run of the session: now_load.sh writes
.claude/state/start_<session> on every SessionStart, close.py writes closed_<session>; the close must be newer
than the start AND no human message may have arrived after it. Anything less (no markers, an unreplaced
${CLAUDE_SESSION_ID}, more work after the close) leaves a note — an extra note is harmless, a missing one is not.
Keeps the newest 5 notes; now_load.sh shows each one once. Markers older than 30 days are removed.
Messages are passed through secret_filter.py before they are written (passwords/keys → [SECRET]).
Always exits 0.
"""
import datetime
import json
import os
import re
import subprocess
import sys

import state_io  # same folder

sys.dont_write_bytecode = True  # no __pycache__ inside .claude/hooks
try:  # passwords/keys must not reach the disk; without the filter the messages are not written at all
    from secret_filter import scrub
except Exception:
    def scrub(_text: str) -> str:
        return "(secret_filter.py missing; message not written for safety)"


def last_human_time(transcript: str):
    """Epoch seconds of the last typed user message. None = unknown: the transcript can't be read,
    has no typed message, or the last one has no valid timestamp. Unknown never counts as "nothing after the close"."""
    last = None
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for s in f:
                try:
                    d = json.loads(s)
                except ValueError:
                    continue
                c = (d.get("message") or {}).get("content")
                typed = isinstance(c, str) or (isinstance(c, list) and any(
                    isinstance(p, dict) and p.get("type") == "text" for p in c))
                if d.get("type") == "user" and typed:
                    try:
                        last = datetime.datetime.fromisoformat(str(d.get("timestamp")).replace("Z", "+00:00")).timestamp()
                    except ValueError:
                        last = None  # this message's time is unknown, so the latest activity is unknown
    except OSError:
        return None
    return last


def last_messages(transcript: str, count: int = 3):
    """The user's last typed messages (tool results and system attachments excluded)."""
    out = []
    try:
        with open(transcript, encoding="utf-8", errors="replace") as f:
            for s in f:
                try:
                    d = json.loads(s)
                except ValueError:
                    continue
                if d.get("type") != "user":
                    continue
                c = (d.get("message") or {}).get("content")
                parts = [c] if isinstance(c, str) else [
                    p.get("text", "") for p in (c or []) if isinstance(p, dict) and p.get("type") == "text"]
                text = " ".join(p for p in parts if p and not p.lstrip().startswith("<")).strip()
                if text:
                    out.append(scrub(" ".join(text.split()))[:200])  # filter first, then cut (no half token)
    except OSError:
        pass
    return out[-count:]


def git(root: str, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10).stdout.rstrip()
    except Exception:
        return ""


def main() -> None:
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR") or inp.get("cwd") or os.getcwd()
    tr = inp.get("transcript_path") or ""
    sid = str(inp.get("session_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        sid = ""
    state = state_io.state_dir(root)
    if not state:
        return  # .claude/state leads outside the project — write nothing
    # Per-project differences via settings.json "env": CLOSE_NOW / CLOSE_PROMPT / CLOSE_GIT (paths relative to root).
    now_path = os.path.join(root, (os.environ.get("CLOSE_NOW") or "NOW.md"))
    git_root = os.path.join(root, (os.environ.get("CLOSE_GIT") or "."))
    if sid:
        started = state_io.regular_mtime(os.path.join(state, f"start_{sid}"))
        closed = state_io.regular_mtime(os.path.join(state, f"closed_{sid}"))
        human = last_human_time(tr) if tr else None
        if started and closed and closed >= started and human is not None and human <= closed:
            return  # close-out proven for this run, and nothing was asked after it
    now = datetime.datetime.now(datetime.timezone.utc)
    next_step = ""
    try:
        section = open(now_path, encoding="utf-8").read().split("## Next ONE step", 1)[1]
        next_step = section.split("\n## ", 1)[0].strip()
    except (OSError, IndexError):
        pass
    messages = [f"- {m}" for m in last_messages(tr)] or ["(unreadable)"]
    lines = [
        f"# Session ended without /close-out · {now:%Y-%m-%d %H:%MZ} · reason={inp.get('reason', '?')}",
        "Mechanical note: NO model summary, lessons or commit. First job: compare this with NOW.md, finish /close-out if needed.",
        "## git status --short", git(git_root, "status", "--short")[:3000] or "(clean or not a git repo)",
        "## git log -3", git(git_root, "log", "-3", "--oneline") or "(none)",
        "## The user's last messages", *messages,
        "## NOW.md — Next ONE step (may be as of session start)", next_step or "(unreadable)",
    ]
    state_io.create(root, "session_end", "\n".join(lines) + "\n", keep=5)
    for pattern in ("start_*", "closed_*"):
        state_io.prune(state, pattern, older_than_days=30)


try:
    main()
except Exception:
    pass
sys.exit(0)
