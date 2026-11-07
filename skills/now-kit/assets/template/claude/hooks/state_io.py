#!/usr/bin/env python3
"""state_io.py — the only way the hooks touch .claude/state/ (logs, markers, notes, snapshots).

Refuses a state folder that leads outside the project through a symlink, never follows a symlink when it
opens a file there, and creates notes under names that can't collide (UTC time + process id + counter, O_EXCL).
Library (imported by the Python hooks): state_dir · write · create · read · regular_mtime · newest · prune.
CLI (for the sh hooks), always exits 0:
  python3 state_io.py <project> touch <name>            create/refresh an empty marker
  python3 state_io.py <project> append <name>           append stdin
  python3 state_io.py <project> create <prefix> [keep]  stdin → new <prefix>_<stamp>.md, keep the newest [keep]
  python3 state_io.py <project> show-notes              print unseen session_end notes once, mark them seen
  python3 state_io.py <project> last-compact            print the newest compact snapshot
"""
import glob
import os
import re
import sys
import time

NAME_OK = re.compile(r"[A-Za-z0-9_.-]+")


def state_dir(root: str):
    """Path of .claude/state under root, created if needed; None if it would lead outside root."""
    real_root = os.path.realpath(root)
    d = os.path.join(root, ".claude", "state")
    real = os.path.realpath(d)
    if os.path.islink(d) or not real.startswith(real_root + os.sep):
        return None
    os.makedirs(d, exist_ok=True)
    if os.path.islink(d) or os.path.realpath(d) != real:
        return None
    return d


# Windows has no O_NOFOLLOW: there a symlink is refused by a check just before opening instead.
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _open(path: str, flags: int) -> int:
    if not NOFOLLOW and os.path.islink(path):
        raise OSError(f"refusing to follow a symlink: {path}")
    return os.open(path, flags | NOFOLLOW, 0o644)


def write(root: str, name: str, text: str, append: bool = False):
    d = state_dir(root)
    if not d or not NAME_OK.fullmatch(name):
        return None
    p = os.path.join(d, name)
    try:
        fd = _open(p, os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC))
    except OSError:
        return None  # e.g. the name is a symlink
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def create(root: str, prefix: str, text: str, keep: int = 0):
    """New file <prefix>_<UTC>Z_<pid>_<n>.md; never replaces an existing file."""
    d = state_dir(root)
    if not d or not NAME_OK.fullmatch(prefix):
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    for n in range(1000):
        p = os.path.join(d, f"{prefix}_{stamp}Z_{os.getpid()}_{n}.md")
        try:
            fd = _open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            continue
        except OSError:
            return None
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if keep:
            prune(d, f"{prefix}_*.md", keep=keep)
        return p
    return None


def read(path: str):
    try:
        fd = _open(path, os.O_RDONLY)
    except OSError:
        return None
    with os.fdopen(fd, encoding="utf-8", errors="replace") as f:
        return f.read()


def regular_mtime(path: str):
    """mtime of a regular file (symlinks don't count); None if missing."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_mtime if not os.path.islink(path) and os.path.isfile(path) else None


def newest(d: str, pattern: str, skip_seen: bool = False):
    files = [p for p in glob.glob(os.path.join(d, pattern))
             if regular_mtime(p) is not None and not (skip_seen and p.endswith(".seen.md"))]
    return sorted(files, key=lambda p: (regular_mtime(p), p), reverse=True)


def prune(d: str, pattern: str, keep: int = 0, older_than_days: float = 0):
    files = sorted(glob.glob(os.path.join(d, pattern)), key=lambda p: (os.lstat(p).st_mtime, p), reverse=True)
    cutoff = time.time() - older_than_days * 86400
    for i, p in enumerate(files):
        if (keep and i >= keep) or (older_than_days and os.lstat(p).st_mtime < cutoff):
            try:
                os.remove(p)  # removes a symlink itself, never its target
            except OSError:
                pass


def cli(argv) -> None:
    if len(argv) < 3:
        return
    root, cmd, args = argv[1], argv[2], argv[3:]
    if cmd == "touch" and args:
        write(root, args[0], "")
    elif cmd == "append" and args:
        write(root, args[0], sys.stdin.read(), append=True)
    elif cmd == "create" and args:
        create(root, args[0], sys.stdin.read(), keep=int(args[1]) if len(args) > 1 else 0)
    elif cmd in ("show-notes", "last-compact"):
        d = state_dir(root)
        if not d:
            return
        if cmd == "last-compact":
            for p in newest(d, "compact_*.md")[:1]:
                print(f"\n--- disk state before compaction ({os.path.basename(p)}) ---")
                print(read(p) or "", end="")
            return
        for p in newest(d, "session_end_*.md", skip_seen=True)[:3]:
            text = read(p)
            if text is None:
                continue
            print(f"\n--- ⚠ a previous session ended without /close-out ({os.path.basename(p)}) ---")
            print(text, end="")
            try:
                os.replace(p, p[:-3] + ".seen.md")
            except OSError:
                pass


if __name__ == "__main__":
    try:
        cli(sys.argv)
    except Exception:  # noqa: BLE001 — a hook helper must never break the session
        pass
    sys.exit(0)
