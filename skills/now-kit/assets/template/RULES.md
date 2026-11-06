# RULES — standing rules (NOT read on start; when needed, `grep -n "<word>" RULES.md`)

Project: {{NAME}} — {{PURPOSE}}
Source: now-kit skill ({{DATE}}); the layout is generalised from two real projects. Project-specific rows are added over time.

## §1 File roles

| file | role | rule |
|---|---|---|
| `NOW.md` (root) | "What now?" — the hook prints it automatically on start | **≤40 lines · overwritten** · `# NOW · YYYY-MM-DD · commit <hash\|none>` + 8 sections: Active task ≤2 · Next ONE step ≤3 · Pending ≤6 · Scheduled ≤2 (`- YYYY-MM-DD: task`) · Background debt ≤3 · Dead ends ≤5 · MISTAKES I MADE ≤5 · Saved to memory ≤1. NO history/rationale/tables; "LATEST", "(old:" FORBIDDEN. Checker: `.claude/hooks/now_check.py` |
| `resume_prompt.md` (root) | opening prompt to paste into a client without hooks | produced by `close.py finish`, overwritten, a single file |
| `RULES.md` (this file) | fixed rules + the full lessons list | opened with grep; changed only by the user's decision |
| `CLAUDE.md` (root) | short instructions loaded every session | ≤30 lines; rules go to RULES, not here |
| `evidence/INDEX.md` + `evidence/*R-{{PREFIX}}-NN*` | decision + evidence index, **permanent** history | rows are never deleted, invalid ones get `~~stale~~` + a pointer · at close-out check this session's receipts are listed |
| `evidence/now_archive/` | old NOW files | not loaded by default, grep it |
| `evidence/DECISIONS.md` | a never-trimmed list of NOW "Dead ends" items and "Decision:" lines | `close.py archive` appends (`decisions.py`); lines are never deleted, one that no longer holds is `~~struck through~~` · not loaded on start, grep it |
| `TODO.md` (root) | deferred work, open decisions, ideas | written when the user says "not now" · items never deleted, `[x]` + receipt when done · not read on start |
| `data/` | raw data, personal data, reports | **not in the repo**; never sent outside; tests don't write here |
| `.claude/` | hooks/skills/rules (in the repo) | `settings.json` 4 events (SessionStart, PreCompact, Stop, SessionEnd) · `state/` logs (ignored; messages/summaries written there pass `secret_filter.py`, your own values: `state/secret_extras.txt`) · `skills/close-out` = `/close-out` · `rules/<area>.md` = rules loaded automatically when that folder is touched |
| `~/.claude/projects/.../memory/` | machine/person specific (file locations, accounts, preferences) | project facts are NOT copied here (they live in the repo) |

## §2 Before writing a claim (no exceptions)

| before writing | required action |
|---|---|
| "Done / it works / committed / installed" | run the check command and see its output (`git log -1`, `git status --short`, the test line). If you didn't see it, write **"not verified"**. The Stop hook logs unproven claims (`.claude/state/claims.log`) |
| "Tests passed" | run the test command, see the result line; numbers come from the output, never typed by hand |
| Any number | measured (command + output) / derived (formula) / estimate? Label: `≈ (derived)`, `≈ estimate`. Compare a new number with the **closest previous measurement** |
| "New finding / first time / root cause" | `grep -n <topic> evidence/INDEX.md` — don't present something already recorded as a discovery |
| A comparison ("X is better / Y% more") | are both sides the same: same period, same unit, same scope? Write numerator and denominator as numbers |
| Rejecting a method/source | the basis is `file:line` / run output, not a summary |
| "None / not found / doesn't work" | look in ALL possible places. **COULDN'T FIND ≠ DOESN'T EXIST** |
| Reporting a measurement/rate/counter | does the source contain your own test rows? Tests never write to real data (use a temp path) |
| Writing a fix | **direction test:** if the fix reduces work or strengthens your claim, confirm it with a second independent source |
| Several questions in one message | count them, answer each, say "didn't check / don't know" for the ones you can't |
| Relaying the user's approval | word for word, with its scope; don't widen it to "approved". Anything that spends money / goes outside / can't be undone needs explicit approval at that moment |
| `git add` | read `git diff --cached --stat`; only your own files; no `data/`, reports, tokens; `add` and `commit` as separate commands |
| Treating a file as "X's answer" | a file name is not evidence; if the user didn't provide it, don't count it as a source |

## §3 Measurement gate — BEFORE writing code / reporting numbers

1. A variable's name ≠ its definition: read the formula, not the name.
2. Denominator: are numerator and denominator over the same period, scope, unit?
3. Calendar and time zone: before saying "started/passed", compute the date and the time zone (your local zone vs UTC).
4. Does the code's own check test the right thing?
When interpreting: don't conclude from a single measurement · scrutinise findings that support your hypothesis harder · if you picked a threshold after seeing the result, say so and repeat on new data.

## §4 Self-review of documents that go outside

Is every number labelled · are both sides of every comparison in the same unit/window · is there a "what this work could NOT do" section · is there more personal data than needed · does any NOW "MISTAKES I MADE" item apply. Write what you find in the document under **"Caught in my own review"**. The document is not sent to anyone without the user's approval.

## §5 Working practice (fixed)

- If there are tests, run them after every change and at close-out. A passing test is not proof — revert the fix and show the test fails.
- **Paid-run order:** small trial → see the result → state ≈ cost → the user's approval at that moment → full run. Every run has a cap.
- Summarise every finding FIRST in everyday language (3-5 sentences), technical detail after. Answers ≤12 lines, ask for one action.
- Read NOW.md from the top before editing it — another session may be running at the same time.
- After every sub-agent: `git diff --stat` + check data files for "did old records disappear".
- Project-specific rules never go into **global** `~/.claude/hooks`.

## §6 MISTAKES I MADE — full list (NOW.md keeps only the latest ≤5)

| date | mistake | lesson |
|---|---|---|

## §7 Never

Write secrets/keys into the chat, code, receipts or repo · paid runs without the user's approval at that moment · commit or send out `data/` contents · email / message / post without approval · `git clean` · `--no-verify` · history/rationale in NOW.md · "LATEST / THIS BLOCK IS VALID" · firm verdicts on unmeasured numbers · "passed" without running tests · in-place `sed` on non-ASCII text files · multiplying `resume_prompt_*` files · touching other projects.
