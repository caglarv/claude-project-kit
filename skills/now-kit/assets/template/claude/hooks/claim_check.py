#!/usr/bin/env python3
"""Stop hook — flags a POSSIBLY unproven claim ("done / tests passed / committed / new finding") in the last answer.
English only. It only WRITES A LOG LINE and never stops Claude: a stopping mode was tried and kept
blocking real test runs written in forms it didn't recognise, so it was removed.

Text inside fenced code blocks (``` or ~~~ at the start of a line) is quoted material (e.g. resume_prompt.md shown at close-out), not a claim,
and is skipped. Each clause is checked on its own, and every kind of claim in it needs its own evidence. A claim that shares a
sentence with a negated clause ("I have not tested and committed …") is only logged as "unknown": the scope of
the negation can't be told reliably.
  test ("tests pass", "passed")      → a test command that was really run (pytest, tests/run.py, npm test …)
  commit ("committed", "pushed")     → git commit / push / log / show / rev-parse
  new finding / root cause           → evidence/INDEX.md or a receipt was read
  other ("done", "fixed", "saved" …) → any of the above, or now_check / close.py / git status / git diff
Evidence = a tool call since the last human message. For Bash only `command` is read, split at && ; | ||:
the evidence command must START a segment (so `echo pytest` or a description doesn't count) and must
come back without an error. If its exit status may not be the call's (a later `;` `|` `||`, an earlier `||`,
or quotes / `$(` that make the split unreliable), or a call mentions tests/git in a form it doesn't
recognise, the result is "unknown".
It sees that a command ran and did not fail, not what it proved — a log line means "look at this".
Transcript unreadable or cut off, no tool calls written yet, a result not written yet, or an exit status that
can't be attributed → "unknown". Log: .claude/state/claims.log ("evidence:NONE" = nothing backed it, "unknown" = can't tell).
"""
import datetime
import json
import os
import re
import sys

import state_io  # same folder

CLAIMS = {
    "finding": r"new finding|for the first time|unexpected(ly)?|discovered|surprising|"
               r"root cause|the real reason|the reason is|the real issue",
    "test": r"tests? (now )?pass(es)?|pass(ed|ing)",
    "commit": r"committed|pushed",
    "other": r"done|fixed|it works|works now|working now|deployed|is live|saved|sent",
}
CLAIM_RE = {k: re.compile(r"\b(" + p + r")\b", re.I) for k, p in CLAIMS.items()}
NEGATION = re.compile(r"n't\b|\b(not|never|unverified|cannot|no longer|yet to)\b|≈ estimate", re.I)
# A fence opens only at the start of a line (as in Markdown), so an inline ``` hides nothing; an unclosed block runs to the end.
CODE_BLOCK = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?(^[ \t]{0,3}\1[ \t]*$|\Z)", re.S | re.M)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
CLAUSE_SPLIT = re.compile(r"[,;:]|\s(?:but|and|while|however|although|though)\s", re.I)

ENV_PREFIX = re.compile(r"^(\w+=\S*\s+)+")
TEST_START = re.compile(
    r"^((\S*/)?(pytest|py\.test)|(uv|poetry|pipenv|hatch|pdm)\s+run\s+((\S*/)?python3?\s+-m\s+)?pytest"
    r"|(\S*/)?python3?(\.\d+)?\s+(-m\s+(pytest|unittest)|\S*(tests?/run\.py|test\S*\.py))"
    r"|npm\s+(run\s+)?test|yarn\s+test|pnpm\s+test|make\s+test|go\s+test|cargo\s+test|tox|nox)\b")
# A Bash segment whose PROGRAM (first word) looks like these but doesn't match the strict forms above is
# doubt, not proof of absence (e.g. ./run_tests.sh). Words printed by echo or a description never count.
LOOSE = {"test": r"test", "commit": r"(^|/)git$", "finding": r"$^", "other": r"test|(^|/)git$|now_check|close\.py"}
GIT_START = re.compile(r"^git\s+(commit|push|log|show|rev-parse)\b")
OTHER_START = re.compile(r"^((\S*/)?python3?\s+\S*(now_check|close)\.py|git\s+(status|diff))\b")
READ_START = re.compile(r"^(grep|rg|cat|head|tail|sed|less|awk)\b")
EVIDENCE_FILE = re.compile(r"evidence/(INDEX\.md|20\d\d-)")
# Source: a lesson from a real project: presenting something already recorded as a discovery,
# and inventing a "root cause" that contradicts the recorded one, both slipped past this gate.


def claims_in(msg):
    """[(kind, word, doubtful)] for every claim in a clause that doesn't negate itself;
    doubtful = another clause of the same sentence is negated."""
    found = []
    for sentence in SENTENCE_SPLIT.split(CODE_BLOCK.sub("\n", msg)):
        clauses = [c for c in CLAUSE_SPLIT.split(sentence or "") if c and c.strip()]
        mixed = any(NEGATION.search(c) for c in clauses)
        for clause in clauses:
            if NEGATION.search(clause):
                continue
            for kind, rx in CLAIM_RE.items():
                m = rx.search(clause)
                if m:
                    found.append((kind, m.group(0), mixed))
    return found


def last_turn(transcript_path):
    """[(name, input, ok)] for tool calls after the last human message; ok = True / False / None (no result yet).
    None if the transcript can't be read or the last human message isn't in the part that was read."""
    try:
        size = os.path.getsize(transcript_path)
        with open(transcript_path, "rb") as f:
            if size > 2_000_000:
                f.seek(size - 2_000_000)
                f.readline()  # drop the partial line
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    records = []
    for line in raw.splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    last_human = -1
    for i, k in enumerate(records):
        if k.get("type") == "user":
            msg = k.get("message", {})
            content = msg.get("content") if isinstance(msg, dict) else None
            # tool_results also come as type=user; count only real text messages
            if isinstance(content, str) or (isinstance(content, list) and any(
                    isinstance(c, dict) and c.get("type") == "text" for c in content)):
                last_human = i
    if last_human < 0:
        return None
    calls, results = [], {}
    for k in records[last_human + 1:]:
        content = (k.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if k.get("type") == "assistant" and c.get("type") == "tool_use":
                calls.append((c.get("id"), c.get("name", ""), c.get("input") or {}))
            elif k.get("type") == "user" and c.get("type") == "tool_result":
                results[c.get("tool_use_id")] = not c.get("is_error", False)
    return [(name, inp, results.get(cid)) for cid, name, inp in calls]


def bash_segments(cmd: str):
    """[(segment, exit_status_is_its_own)]. True only when the call's success must include this segment:
    it isn't reached through `||`, only `&&` follows it, and (unless it's the first) no quotes or `$(` /
    backticks could have hidden a separator inside a string."""
    parts = re.split(r"(&&|\|\||;|\||\n)", cmd)
    quoted = any(q in cmd for q in ("'", '"', "`", "$("))
    out = []
    for k, i in enumerate(range(0, len(parts), 2)):
        seg = ENV_PREFIX.sub("", parts[i].strip())
        if not seg:
            continue
        prev = parts[i - 1] if i else ""
        own = prev != "||" and all(sep == "&&" for sep in parts[i + 1::2]) and (k == 0 or not quoted)
        out.append((seg, own))
    return out


def fits(kind, name, inp):
    """'own' (its exit status decides the call), 'hidden' (it ran but a later ; | || decides), or None."""
    if name in ("Read", "Grep"):
        target = str(inp.get("file_path") or inp.get("path") or "")
        return "own" if kind in ("finding", "other") and EVIDENCE_FILE.search(target) else None
    if name != "Bash":
        return None
    best = None
    for seg, own in bash_segments(str(inp.get("command") or "")):
        if kind == "finding":
            hit = READ_START.search(seg) and EVIDENCE_FILE.search(seg)
        elif kind == "test":
            hit = TEST_START.search(seg)
        elif kind == "commit":
            hit = GIT_START.search(seg)
        else:
            hit = TEST_START.search(seg) or GIT_START.search(seg) or OTHER_START.search(seg)
        if hit:
            if own:
                return "own"
            best = "hidden"
    return best


def verdict(kind, calls):
    """'yes' / 'no' / 'unknown' — is there a successful call that backs this kind of claim?"""
    if not calls:
        return "unknown"  # the turn's tool calls may not be written to the transcript yet
    doubt = False
    for name, inp, ok in calls:
        f = fits(kind, name, inp)
        if ok is None:
            doubt = True  # a result not written yet could be the evidence
        elif f == "own" and ok:
            return "yes"
        elif f == "hidden" or (f == "own" and kind == "finding"):
            doubt = True  # looked/ran, but the exit status doesn't tell
        elif f is None and name == "Bash" and any(
                re.search(LOOSE[kind], (seg.split() or [""])[0], re.I)
                for seg, _ in bash_segments(str(inp.get("command") or ""))):
            doubt = True  # runs something test/git-like in a form we don't recognise
    return "unknown" if doubt else "no"


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return 0
    msg = d.get("last_assistant_message") or ""
    claims = claims_in(msg)
    if not claims:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or d.get("cwd") or os.getcwd()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    summary = re.sub(r"\s+", " ", msg)[:80]
    calls = last_turn(d.get("transcript_path", ""))
    if calls is None:
        state_io.write(root, "claims.log", f"{ts} · {claims[0][1]} · unknown (transcript unreadable or cut off) · {summary}\n", append=True)
        return 0
    unproven, unknown = [], []
    for kind, word, doubtful in claims:
        v = verdict(kind, calls)
        if v == "no" and doubtful:
            v = "unknown"
        if v == "no":
            unproven.append(word)
        elif v == "unknown":
            unknown.append(word)
    if unproven:
        state_io.write(root, "claims.log", f"{ts} · {', '.join(unproven)} · evidence:NONE · {summary}\n", append=True)
    if unknown:
        state_io.write(root, "claims.log", f"{ts} · {', '.join(unknown)} · unknown · {summary}\n", append=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — never let the Stop hook lock up
        sys.exit(0)
