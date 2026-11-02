#!/usr/bin/env python3
"""close_reminder.py — Stop hook. Reminds about /close-out when the chat grows large; NEVER blocks.

Context = input + cache_read + cache_creation tokens of the last assistant reply (read from the transcript).
Thresholds: CLOSE_REMIND_TOKENS (default 300000) and 2x that. ONE warning per threshold per session.
Marker file: .claude/state/reminder_<session>.txt (outside git).
Why: in a long chat left idle, a cold prompt cache made a single message cost several dollars.
Always exits 0.
"""
import json
import os
import re
import sys

import state_io  # same folder


def last_context(transcript: str):
    """Finds the last usage block scanning back from the end of the transcript; None if not found."""
    try:
        with open(transcript, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2_000_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for s in reversed(lines):
        try:
            d = json.loads(s)
        except ValueError:
            continue
        u = (d.get("message") or {}).get("usage") if isinstance(d, dict) else None
        if isinstance(u, dict) and d.get("type") == "assistant":
            return sum(int(u.get(k) or 0) for k in
                       ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    return None


def main() -> None:
    try:
        inp = json.load(sys.stdin)
    except ValueError:
        return
    sid = str(inp.get("session_id") or "")
    tr = inp.get("transcript_path") or ""
    if not sid or not tr:
        return
    threshold = int(os.environ.get("CLOSE_REMIND_TOKENS", "300000"))
    n = last_context(tr)
    if n is None or n < threshold:
        return
    level = 2 if n >= 2 * threshold else 1
    root = os.environ.get("CLAUDE_PROJECT_DIR") or inp.get("cwd") or os.getcwd()
    state = state_io.state_dir(root)
    if not state or not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        return
    try:
        previous = int((state_io.read(os.path.join(state, f"reminder_{sid}.txt")) or "0").strip() or 0)
    except ValueError:
        previous = 0
    if level <= previous:
        return
    if not state_io.write(root, f"reminder_{sid}.txt", str(level)):
        return
    k = round(n / 1000)
    message = (f"This chat has reached ≈{k}k tokens. After a break the prompt cache goes cold and a single message gets expensive. "
               "If the work is done, run /close-out and continue in a new chat.")
    print(json.dumps({"systemMessage": message}, ensure_ascii=False))


try:
    main()
except Exception:
    pass
sys.exit(0)
