#!/usr/bin/env python3
"""setup.py — the mechanical part of the now-kit skill.

  python3 setup.py <target-folder> --name "Name" --purpose "one sentence" --prefix XX [--no-git]
      Copies the template (../assets/template) into the target. NEVER OVERWRITES AN EXISTING FILE (skips and lists it).
      Fills in {{NAME}} {{PURPOSE}} {{PREFIX}} {{DATE}} {{DATE_SHORT}}. Runs `git init` if it isn't a git repo
      (NO commit — the first commit happens at /close-out). Refuses to write through symlinks that leave the target.
      Placeholders are filled in ONE pass, so text the user typed is never treated as a placeholder.
      Verifies at the end: now_check OK · settings.json really runs every hook and hooks aren't disabled ·
      .gitignore (as git itself evaluates it) keeps secrets/data out · scripts compile. The last line is the verdict.
  python3 setup.py <project-folder> --compare
      READ-ONLY: compares the project's .claude/hooks + skills/close-out files with the template (SAME / DIFFERENT / MISSING).
Exit code: 0 ok · 1 verification or input error.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

TEMPLATE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "template"))
TEXT = (".md", ".py", ".sh", ".json", "")
PLACEHOLDER = re.compile(r"\{\{(NAME|NAME_PY|PURPOSE|PREFIX|DATE|DATE_SHORT)\}\}")
ANY_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
EXTRA_DIRS = ("evidence/now_archive", ".claude/rules", "data")
NO_LINKS = (".claude/state",)  # created later by the hooks; must not lead outside either
# A pre-existing settings.json / .gitignore is never overwritten, so verify() checks it still does the job.
# Paths git must ignore: the folders themselves plus typical files inside them (a "*.csv" rule alone is not enough).
MUST_IGNORE = [".env", ".env.local", "data/", "data/private.json", "data/sub/notes.md",
               ".claude/state/", ".claude/state/session_end_sample.md", ".claude/state/claims.log"]
ALLOWED_TRACKED = {".env.example"}  # the template's gitignore keeps it in git on purpose (!.env.example)
MUST_KEEP = [".claude/settings.json", ".claude/hooks/now_load.sh", ".claude/skills/close-out/SKILL.md"]


def target_path(rel: str) -> str:
    """template/claude/... → .claude/... ; template/gitignore → .gitignore (so hidden files stay visible in the template)."""
    parts = rel.split(os.sep)
    if parts[0] == "claude":
        parts[0] = ".claude"
    if parts == ["gitignore"]:
        parts = [".gitignore"]
    return os.path.join(*parts)


def template_files():
    for root, _, files in os.walk(TEMPLATE):
        for f in sorted(files):
            if f == ".DS_Store":
                continue
            full = os.path.join(root, f)
            yield full, target_path(os.path.relpath(full, TEMPLATE))


def fill(text: str, values: dict) -> str:
    """One pass: an inserted value is never scanned again, so a name like "{{PURPOSE}}" stays literal."""
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], text)


def inside(path: str, root: str) -> bool:
    """True if `path`, with every existing symlink resolved, stays under `root` (already resolved)."""
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def setup(a) -> int:
    target = os.path.abspath(a.target)
    if not re.fullmatch(r"[A-Z]{2,4}", a.prefix or ""):
        print("ERROR --prefix must be 2-4 capital letters (e.g. BL, WEB, ABC)")
        return 1
    for flag, value in (("--name", a.name), ("--purpose", a.purpose)):
        if any(ord(c) < 32 for c in value):
            print(f"ERROR {flag} must be a single line of text")
            return 1
    today = datetime.date.today()
    values = {"NAME": a.name, "NAME_PY": repr(a.name), "PURPOSE": a.purpose, "PREFIX": a.prefix,
              "DATE": today.isoformat(), "DATE_SHORT": today.strftime("%m-%d")}
    os.makedirs(target, exist_ok=True)
    root = os.path.realpath(target)
    files = list(template_files())
    outside = [rel for _, rel in files if not inside(os.path.join(target, rel), root)]
    outside += [d for d in EXTRA_DIRS + NO_LINKS if not inside(os.path.join(target, d), root)]
    if outside:
        print("ERROR these paths lead outside the target folder through a symlink; nothing was written:")
        for rel in outside:
            print(f"  {rel}")
        return 1

    written, skipped = [], []
    for source, rel in files:
        dst = os.path.join(target, rel)
        if os.path.lexists(dst):
            skipped.append(rel)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.splitext(source)[1] in TEXT:
            with open(source, encoding="utf-8") as f:
                content = fill(f.read(), values)
            with open(dst, "x", encoding="utf-8") as f:
                f.write(content)
        else:
            with open(source, "rb") as f, open(dst, "xb") as g:
                g.write(f.read())
        if rel.startswith(os.path.join(".claude", "hooks")):
            os.chmod(dst, 0o755)
        written.append(rel)
    for folder in EXTRA_DIRS:
        os.makedirs(os.path.join(target, folder), exist_ok=True)

    git_ok, git_note = True, "git: skipped (--no-git)"
    if not a.no_git:
        git_ok, git_note = init_git(target, root)

    print(f"written {len(written)} files · skipped (already existed, untouched) {len(skipped)}")
    for r in skipped:
        print(f"  skipped: {r}")
    print(git_note)
    problems, summary = verify(target)
    if not git_ok:
        problems.append(git_note)
    return report(problems, summary)


def report(problems: list, summary: str) -> int:
    """The single place that prints the verdict; it is always the last line."""
    if problems:
        print("problems:")
        for s in problems:
            print(f"  {s}")
        print(f"VERIFICATION FAILED · {len(problems)} problem(s) above")
        return 1
    print(f"VERIFICATION OK · {summary}")
    return 0


def init_git(target: str, root: str):
    """Returns (ok, note). Missing git is a warning (git is optional); a failed init is an error."""
    if not shutil.which("git"):
        return True, "git: not found — skipped (install git to get the close-out commit)"
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=target,
                         capture_output=True, text=True).stdout.strip()
    if top:
        if os.path.realpath(top) == root:
            return True, "git: already a repo"
        return True, f"git: inside an existing repo at {top} — no new repo created"
    r = subprocess.run(["git", "init", "-q"], cwd=target, capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"git: init FAILED {r.stderr.strip()}"
    return True, "git: initialised (no commit)"


def template_settings() -> dict:
    return json.load(open(os.path.join(TEMPLATE, "claude", "settings.json"), encoding="utf-8"))


def hook_problems(target: str) -> list:
    """Every command of the template must be registered as a command hook, for the same event, with a matcher
    that is absent, "*" or the template's own. Hooks must not be disabled in settings.json or settings.local.json."""
    problems = []
    try:
        cfg = json.load(open(os.path.join(target, ".claude", "settings.json"), encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        return [f"settings.json: {exc}"]
    for name in ("settings.json", "settings.local.json"):
        try:
            extra = cfg if name == "settings.json" else json.load(
                open(os.path.join(target, ".claude", name), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(extra, dict) and extra.get("disableAllHooks"):
            problems.append(f"{name}: disableAllHooks is true — none of the hooks would run")
    hooks = cfg.get("hooks") if isinstance(cfg.get("hooks"), dict) else {}
    missing, custom = [], []
    for event, groups in template_settings()["hooks"].items():
        have = hooks.get(event) if isinstance(hooks.get(event), list) else []
        for tgroup in groups:
            for th in tgroup["hooks"]:
                ok = any(isinstance(g, dict) and g.get("matcher", "") in ("", "*", tgroup.get("matcher", ""))
                         and any(isinstance(h, dict) and h.get("type") == "command" and h.get("command") == th["command"]
                                 for h in (g.get("hooks") or []))
                         for g in have)
                if not ok:
                    script = th["command"].rsplit("/", 1)[-1].strip('"')
                    if script in json.dumps(have):
                        custom.append(f"{event}: {script}")
                    else:
                        missing.append(f"{event}: {th['command']}")
    if custom:
        problems.append("customised hook command could not be verified automatically (it must match the template "
                        "exactly, including `sh`/`python3`): " + "; ".join(custom))
    if missing:
        problems.append("settings.json does not run these hooks (merge the 'hooks' block from "
                        f"{os.path.join(TEMPLATE, 'claude', 'settings.json')}): " + "; ".join(missing))
    return problems


def check_ignores(repo: str) -> list:
    """Runs git check-ignore in `repo` (git applies the last matching rule and negations itself)."""
    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", "--no-index", path], cwd=repo).returncode == 0
    out = []
    not_ignored = [p for p in MUST_IGNORE if not ignored(p)]
    kept_out = [p for p in MUST_KEEP if ignored(p)]
    if not_ignored:
        out.append(".gitignore does not keep these out of git: " + ", ".join(not_ignored)
                   + " (add `.env`, `.env.*`, `data/`, `.claude/state/` — see the template's gitignore)")
    if kept_out:
        out.append(".gitignore hides kit files that belong in git: " + ", ".join(kept_out))
    return out


def ignore_problems(target: str):
    """Returns (problems, status). Asks git itself: in the project's repo if there is one, otherwise in a scratch
    repo holding a copy of the .gitignore. Without git it can only vouch for the template's own .gitignore."""
    path = os.path.join(target, ".gitignore")
    if not os.path.exists(path):
        return [".gitignore is missing"], ""
    if not shutil.which("git"):
        own = fill(open(os.path.join(TEMPLATE, "gitignore"), encoding="utf-8").read(), {})
        if open(path, encoding="utf-8").read() == own:
            return [], ".gitignore ok (the kit's own)"
        print("warning: git is not installed, so the existing .gitignore could not be checked")
        return [], ".gitignore not verified (no git)"
    inside = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=target,
                            capture_output=True, text=True).stdout.strip() == "true"
    if inside:
        out = check_ignores(target)
        tracked = [f for f in subprocess.run(["git", "ls-files", "--", ".env", ".env.*", "data", ".claude/state"],
                                             cwd=target, capture_output=True, text=True).stdout.split()
                   if f not in ALLOWED_TRACKED]
        if tracked:
            out.append("already tracked by git (remove with `git rm --cached`): " + ", ".join(tracked))
        return out, ".gitignore ok"
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run(["git", "init", "-q"], cwd=scratch, capture_output=True)
        shutil.copyfile(path, os.path.join(scratch, ".gitignore"))
        return check_ignores(scratch), ".gitignore ok"


def verify(target: str):
    """Returns (problems, summary)."""
    problems = []
    r = subprocess.run([sys.executable, os.path.join(target, ".claude", "hooks", "now_check.py"),
                        os.path.join(target, "NOW.md")], capture_output=True, text=True)
    nc = (r.stdout or r.stderr).strip()
    if not nc.startswith("OK"):
        problems.append(f"now_check: {nc}")
    problems += hook_problems(target)
    ignore_found, ignore_status = ignore_problems(target)
    problems += ignore_found
    hooks = os.path.join(target, ".claude", "hooks")
    for f in sorted(os.listdir(hooks)):
        if f.endswith(".py"):
            try:  # syntax only; writes no .pyc
                compile(open(os.path.join(hooks, f), encoding="utf-8").read(), f, "exec")
            except SyntaxError as exc:
                problems.append(f"{f}: line {exc.lineno} {exc.msg}")
    unknown = set()
    for source, _ in template_files():
        try:
            unknown |= {m for m in ANY_PLACEHOLDER.findall(open(source, encoding="utf-8").read())
                        if not PLACEHOLDER.fullmatch("{{" + m + "}}")}
        except (UnicodeDecodeError, OSError):
            pass
    if unknown:
        problems.append("template uses unknown placeholders: " + ", ".join(sorted(unknown)))
    return problems, f"now_check {nc} · hooks registered · {ignore_status} · scripts compile"


def compare(project: str) -> int:
    project = os.path.abspath(project)
    if not os.path.isdir(os.path.join(project, ".claude")):
        print(f"ERROR no .claude/ in {project}")
        return 1
    for source, rel in template_files():
        if not rel.startswith(".claude"):
            continue
        dst = os.path.join(project, rel)
        if not os.path.exists(dst):
            print(f"MISSING    {rel}")
            continue
        a = open(source, encoding="utf-8").read()
        b = open(dst, encoding="utf-8").read()
        if a == b:
            print(f"SAME       {rel}")
        else:
            note = " (expected: project name/prefix were filled in)" if "{{" in a else ""
            print(f"DIFFERENT  {rel}{note}")
    return 0


ap = argparse.ArgumentParser()
ap.add_argument("target")
ap.add_argument("--name")
ap.add_argument("--purpose", default="(to be filled in by the user)")
ap.add_argument("--prefix")
ap.add_argument("--no-git", action="store_true")
ap.add_argument("--compare", action="store_true")
a = ap.parse_args()
if a.compare:
    sys.exit(compare(a.target))
if not a.name or not a.prefix:
    ap.error("--name and --prefix are required for setup")
sys.exit(setup(a))
