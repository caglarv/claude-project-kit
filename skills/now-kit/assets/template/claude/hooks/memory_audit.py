#!/usr/bin/env python3
"""memory_audit.py — audits the project's memory READ-ONLY; it never changes or deletes a file.

Looks at ~/.claude/projects/<project>/memory/ (MEMORY.md + note files) and the RULES.md §6 lessons table.
Four kinds of problems:
  1. index: a MEMORY.md line whose file is missing · a note file that MEMORY.md doesn't list
  2. duplicate: two notes or two lessons that say nearly the same thing (could they be merged?)
  3. dead path: a project file a note names no longer exists (`src/x.py` style; server paths like /etc are skipped)
  4. old: a note not updated for more than 120 days (is it still true?)
The decision is always the user's/assistant's; the script only lists. Run in step 6 of /close-out.

  python3 .claude/hooks/memory_audit.py [--root PROJECT] [--memory DIR] [--days 120]
Exit code is always 0 (never stops a close-out). Last line: `MEMORY OK` or `MEMORY <N> warning(s)`.
Idea from avenoxbeyin beyin_v3_audit.py (MIT, Avenox 2026); code written anew for this kit.
"""
import argparse
import datetime
import glob
import os
import re
import sys
import unicodedata

H = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.normpath(os.path.join(H, "..", ".."))

STOP = set("""the a an and or of to in on for is are be was were with as at by it its this that these those not no
from but if then than so do does did has have had can will would should may might must also only just more most
very all any each every some such into over under after before about which who what when where how why""".split())
PATH_IN_CODE = re.compile(r"`([^`\s<>*|]+)`")
EXT = re.compile(r"\.(py|md|sh|json|ya?ml|csv|txt|toml|js|ts|html)$", re.I)
LINK = re.compile(r"\]\(([^)\s]+\.md)\)")


def fold(text: str) -> str:
    m = unicodedata.normalize("NFC", text).casefold()
    return unicodedata.normalize("NFKD", m).encode("ascii", "ignore").decode()


def words(text: str) -> set:
    """Rough stems: first 5 letters of each word (drops most suffixes). Numbers and short words are skipped."""
    out = set()
    for w in re.findall(r"[a-z0-9]+", fold(text)):
        if len(w) < 3 or w.isdigit() or w in STOP:
            continue
        out.add(w[:5])
    return out


def similarity(a: set, b: set):
    if len(a) < 6 or len(b) < 6:
        return 0.0, 0.0
    common = len(a & b)
    return common / len(a | b), common / min(len(a), len(b))


def memory_dir(root: str):
    """Claude Code's naming: every non letter/digit character of the path becomes '-'. macOS NFD paths are tried too."""
    base = os.path.expanduser("~/.claude/projects")
    for form in ("NFC", "NFD"):
        name = re.sub(r"[^A-Za-z0-9]", "-", unicodedata.normalize(form, os.path.abspath(root)))
        path = os.path.join(base, name, "memory")
        if os.path.isdir(path):
            return path
    return None


def front_matter(text: str):
    """(front matter dict, body). Without front matter: ({}, text)."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("\n---", 1)
    if len(parts) < 2:
        return {}, text
    fields = {}
    for s in parts[0].splitlines()[1:]:
        m = re.match(r"^\s*([A-Za-z_]+):\s*(.*)$", s)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"\'')
    return fields, parts[1]


def lessons(root: str):
    """(date, mistake+lesson) rows of the RULES.md §6 table."""
    candidates = [os.path.join(root, "RULES.md")]
    if os.environ.get("CLOSE_NOW"):  # a project whose NOW.md lives in a subfolder keeps RULES.md beside it
        candidates.append(os.path.join(root, os.path.dirname(os.environ["CLOSE_NOW"]), "RULES.md"))
    text = None
    for path in candidates:
        try:
            text = open(path, encoding="utf-8").read()
            break
        except OSError:
            continue
    if text is None:
        return []
    m = re.search(r"^## §6.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return []
    out = []
    for s in m.group(1).splitlines():
        cells = [c.strip() for c in s.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] not in ("date", "") and not set(cells[0]) <= set("-: "):
            out.append((cells[0], " ".join(cells[1:])))
    return out


def audit(root: str, memory, days: int):
    warnings = []
    notes = {}
    if memory and os.path.isdir(memory):
        for path in sorted(glob.glob(os.path.join(memory, "*.md"))):
            name = os.path.basename(path)
            if name == "MEMORY.md":
                continue
            try:
                notes[name] = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
        # 1. index consistency
        try:
            index = open(os.path.join(memory, "MEMORY.md"), encoding="utf-8").read()
        except OSError:
            index = None
        if index is None and notes:
            warnings.append(f"index: no MEMORY.md but {len(notes)} note(s)")
        elif index is not None:
            linked = {os.path.basename(l) for l in LINK.findall(index)}
            for name in sorted(linked - set(notes)):
                warnings.append(f"index: MEMORY.md points to '{name}' but the file is missing")
            for name in sorted(set(notes) - linked):
                if name in index:
                    continue  # not linked, but its name is written in MEMORY.md (a pointer from another line)
                warnings.append(f"index: '{name}' is not listed in MEMORY.md (never seen on start)")

    # 2. duplicates — notes among themselves, lessons among themselves
    def find_duplicates(entries, kind):
        sets = [(name, words(text)) for name, text in entries]
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                jac, cont = similarity(sets[i][1], sets[j][1])
                if jac >= 0.5 or cont >= 0.8:
                    warnings.append(f"duplicate ({kind}): '{sets[i][0]}' ≈ '{sets[j][0]}' "
                                    f"(overlap {round(cont * 100)}%) — merge them?")

    find_duplicates([(n, front_matter(t)[1] + " " + front_matter(t)[0].get("description", "")) for n, t in notes.items()],
                    "memory")
    find_duplicates([(f"§6 {d} · {x[:40]}…", x) for d, x in lessons(root)], "lesson")

    # 3. dead paths — project-relative paths and ~/ paths only. Code often lives in a subfolder:
    # the root, CLOSE_GIT and every first-level subfolder of the root are tried.
    bases = [root]
    if os.environ.get("CLOSE_GIT"):
        bases.append(os.path.join(root, os.environ["CLOSE_GIT"]))
    try:
        bases += [os.path.join(root, d) for d in sorted(os.listdir(root))
                  if not d.startswith(".") and os.path.isdir(os.path.join(root, d))]
    except OSError:
        pass
    for name, text in notes.items():
        if name.startswith("ref_") or not front_matter(text)[0]:
            continue  # research reports (ref_ / no front matter) mention other systems' paths; skipped
        for raw in sorted(set(PATH_IN_CODE.findall(front_matter(text)[1]))):
            path = raw.rstrip(".,;:)")
            if ("://" in path or path.startswith(("/", "$", "-")) or "{" in path or ".." in path
                    or re.search(r"YYYY|XXX|<|\.\.\.", path)):
                continue
            path = path.split("#")[0].split(":")[0]  # file.py:42 or file.md#section
            if "/" not in path or not EXT.search(path):
                continue  # a bare name (e.g. `NOW.md`) could be anywhere — not checked
            if path.startswith("~"):
                found = os.path.exists(os.path.expanduser(path))
            else:
                found = any(os.path.exists(os.path.join(b, path)) for b in bases)
            if not found:
                warnings.append(f"dead path: '{name}' → `{path}` not found (moved or deleted?)")

    # 4. old
    today = datetime.datetime.now(datetime.timezone.utc)
    for name, text in notes.items():
        stamp = front_matter(text)[0].get("modified", "")
        try:
            t = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            try:
                t = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(memory, name)),
                                                    datetime.timezone.utc)
            except (OSError, TypeError):
                continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        age = (today - t).days
        if age > days:
            warnings.append(f"old: '{name}' not updated for {age} days — still true?")
    return notes, warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Read-only audit of the project's memory")
    ap.add_argument("--root", default=DEFAULT_ROOT)
    ap.add_argument("--memory")
    ap.add_argument("--days", type=int, default=120)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    memory = a.memory or memory_dir(root)
    notes, warnings = audit(root, memory, a.days)
    print(f"memory: {memory or '(no folder)'} · {len(notes)} note(s) · {len(lessons(root))} lesson(s)")
    for w in warnings[:25]:
        print(f"  - {w}")
    if len(warnings) > 25:
        print(f"  … and {len(warnings) - 25} more")
    print("MEMORY OK" if not warnings else f"MEMORY {len(warnings)} warning(s) (information only; no file was changed)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"MEMORY audit skipped ({type(exc).__name__}: {exc})")
        sys.exit(0)
