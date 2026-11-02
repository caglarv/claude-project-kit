# {{NAME}} · project instructions

Purpose: {{PURPOSE}}
Independent of the user's other projects; do not touch them.

## On start
- `NOW.md` arrives automatically via the SessionStart hook (new chat, resume, /clear, after compaction). First job: "Next ONE step".
  Open other files only if that step needs them. History lives in `evidence/INDEX.md`; rules in `RULES.md` (grep it, don't read it top to bottom).
- **Preserve during context compaction:** active task · the REAL result of the last command (pass/fail, numbers) · files touched ·
  unverified claims · the user's decisions word for word. Afterwards NOW.md + the pre-compaction disk snapshot are loaded;
  if the chat and the files disagree, the files + `git status` win.

## While working
- Summarise every finding FIRST in plain everyday language (3-5 sentences: what happened, why it matters, where things stand); technical detail after.
- Before writing a claim, `grep -n "<word>" RULES.md` (§2 table). Before saying "new finding", `grep -n <topic> evidence/INDEX.md`.
- "Done / passed / saved" only after seeing the command output; if you didn't see it, say "not verified". The Stop hook logs unproven claims.
- Deferred work and ideas → `TODO.md`. Any step that spends money / goes outside / can't be undone = first ≈ cost + the user's approval.
- Close-out: if the user says "start the close-out", run the `/close-out` skill.

## Never
Write secrets/keys into the chat or the repo · paid runs without approval · sending anything (email, message, post) without approval · committing `data/` · `git clean` / `--no-verify` · in-place `sed` on non-ASCII text files · putting project-specific rules into global `~/.claude/hooks`.

## Skills — check on every task
- Before starting, look at the installed skill list. If a skill fits the request (PDF, Word, Excel, slides, scheduled task, research, design/page, code review, etc.), load it and follow it BEFORE doing the work with plain tools.
- Don't skip a fitting skill because "the job is simple". This applies even if the user doesn't name the skill.
