#!/bin/sh
# PreCompact (manual|auto) — records the DISK state right before the context is compacted.
# It can't record what's in the model's head (hook stdout doesn't reach the model); the
# compaction instruction in CLAUDE.md covers that. now_load.sh prints this file back on SessionStart(compact).
# Keeps the newest 5 snapshots. Always exits 0 (never blocks compaction).
D="${CLAUDE_PROJECT_DIR:-$PWD}"
H="$D/.claude/hooks"
TRIG="$(python3 -c 'import sys,json; print(json.load(sys.stdin).get("trigger",""))' 2>/dev/null)"
# state_io.py writes it under a name that can't collide and keeps the newest 5.
{
  printf '# Disk state before compaction · %s · trigger=%s\n' "$(date -u '+%Y-%m-%d %H:%MZ')" "${TRIG:-?}"
  printf '## git status --short\n'; (cd "$D" && git status --short 2>/dev/null | head -30)
  printf '## git log -3\n'; (cd "$D" && git log -3 --oneline 2>/dev/null)
  printf '## git diff --stat (last line)\n'; (cd "$D" && git diff --stat 2>/dev/null | tail -1)
  printf '## files changed in the last 3 hours\n'
  (cd "$D" && find . -type f -mmin -180 -not -path "./.git/*" -not -path "./.venv/*" -not -path "./data/*" -not -path "*/state/*" -not -name ".DS_Store" 2>/dev/null | head -30)
  printf '## NOW.md — Next ONE step\n'
  awk '/^## Next ONE step/{f=1;next} /^## /{f=0} f' "$D/NOW.md" 2>/dev/null
} 2>/dev/null | python3 "$H/state_io.py" "$D" create compact 5 2>/dev/null
exit 0
