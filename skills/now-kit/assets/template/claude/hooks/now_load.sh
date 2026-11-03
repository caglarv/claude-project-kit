#!/bin/sh
# SessionStart (every source: startup|resume|clear|compact|fork) — check the root NOW.md and print it into context.
# Only $CLAUDE_PROJECT_DIR/NOW.md (NO other candidate paths — avoids path-mismatch bugs).
# Always exits 0: this hook never blocks the session.
D="${CLAUDE_PROJECT_DIR:-$PWD}"
NOW="$D/NOW.md"
[ -f "$NOW" ] || exit 0
H="$D/.claude/hooks"
# PY: first working Python 3.9+ (python3, py -3, python) — see py.sh; Windows has no reliable `python3`.
PY() { sh "$H/py.sh" "$@"; }
# Everything under .claude/state goes through state_io.py (no symlinks followed, no outside writes).
S() { PY "$H/state_io.py" "$D" "$@" 2>/dev/null; }

# source and session_id from stdin JSON — stay empty without python, harmless
IN="$(PY -c 'import sys,json; d=json.load(sys.stdin); print(d.get("source",""), d.get("session_id",""))' 2>/dev/null)"
SRC="${IN%% *}"; SID="${IN#* }"
# start_<session>: when this run of the session began; safety_net.py compares the close-out marker with it.
case "$SID" in ""|*[!A-Za-z0-9_-]*) ;; *) S touch "start_$SID" ;; esac

r="$(PY "$H/now_check.py" "$NOW" 2>&1)"; code=$?
n="$(printf '%s' "$r" | awk 'NR==1{print $2}')"
printf '%s · %s · code=%s · %s\n' "$(date '+%Y-%m-%d %H:%M')" "${SRC:-?}" "$code" "$(printf '%s' "$r" | head -1)" | S append now_size.log

PY "$H/due_dates.py" "$NOW" 2>/dev/null

# Decide on the output text, not the exit code: if the checker crashes (traceback,
# syntax error) it must not be mistaken for "BROKEN" — avoids false alarms.
case "$r" in
  OK*)
    cat "$NOW"
    printf '\n[NOW.md %s lines · %s — do the "Next ONE step"; open other files only if that step needs them. Rules: RULES.md (via grep)]\n' "$n" "$(printf '%s' "$r" | head -1)" ;;
  BROKEN*)
    printf '⚠ NOW.md BROKEN: %s\nFIRST JOB: rewrite NOW.md to the template (RULES.md §1); start nothing else.\n--- first 40 lines ---\n' "$r"
    head -40 "$NOW" ;;
  *)
    printf '⚠ NOW.md checker did not run (code=%s): %s\nNOW.md is still below; fix the checker but do not block work.\n' "$code" "$(printf '%s' "$r" | tail -2 | tr '\n' ' ')"
    head -40 "$NOW" ;;
esac

# After compaction: the disk snapshot. Otherwise: safety_net.py notes, each shown once, then marked seen.
if [ "$SRC" = "compact" ]; then
  S last-compact
else
  S show-notes
fi
exit 0
