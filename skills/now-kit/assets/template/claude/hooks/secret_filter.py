#!/usr/bin/env python3
"""secret_filter.py — replaces passwords, API keys and tokens with "[SECRET]" before text is written to disk.

Used by safety_net.py (the user's last messages), claim_check.py (log summary) and decisions.py.
No network, no model, regular expressions only. A false positive is harmless (a word becomes "[SECRET]");
a false negative is not, so the formats are broad.
Your own literal values (e.g. a client password): .claude/state/secret_extras.txt, one value per line,
'#' starts a comment. Without that file only the built-in formats apply.
Pattern list adapted from avenoxbeyin beyin_v3_secrets.py — MIT License, Copyright (c) 2026 Avenox.
CLI: `echo text | python3 secret_filter.py` prints the filtered text (for testing).
"""
import os
import re
import sys

LABEL = "[SECRET]"

_KEY_NAME = r"(?:api[_ -]?key|apikey|access[_ -]?token|auth[_ -]?token|token|secret|client[_ -]?secret|password|passwd|passphrase)"

PATTERNS = (
    # PEM private key block (whole) and a bare header
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    # user:password@ inside a URL
    re.compile(r"(?<=://)[^/\s?#:@]*:[^/\s?#@]+(?=@)"),
    # ?token=... &password=...
    re.compile(r"(?i)(?<=[?&])" + _KEY_NAME + r"=[^&\s]{6,}"),
    # api_key = "...", PASSWORD: xyz, "token": "..."  (value ≥8 chars)
    re.compile(r"""(?i)(?<![A-Za-z0-9_])["']?[A-Za-z0-9_]*""" + _KEY_NAME +
               r"""[A-Za-z0-9_]*["']?\s*[:=]\s*(?:"[^"\s]{8,}"|'[^'\s]{8,}'|[^\s"',;]{8,})"""),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{34}(?![A-Za-z0-9])"),
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,255}(?![A-Za-z0-9_-])"),   # OpenAI / Anthropic
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,255}\b"),                   # Stripe
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),                                 # AWS
    re.compile(r"\bxox[abeoprs]-[0-9]+-[A-Za-z0-9-]{8,255}\b"),                   # Slack
    re.compile(r"\bxapp-[0-9]+-[A-Za-z0-9-]{8,255}\b"),
    re.compile(r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])"),      # Google
    re.compile(r"\bnpm_[A-Za-z0-9]{36}(?![A-Za-z0-9])"),
    re.compile(r"\bapify_api_[A-Za-z0-9]{20,}\b"),                                # Apify
    re.compile(r"(?<![A-Za-z0-9_.-])SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),  # SendGrid
    re.compile(r"\b[0-9]{8,10}:[A-Za-z0-9_-]{35}(?![A-Za-z0-9_-])"),               # Telegram bot
    # JWT: eyJ… three dot-separated parts
    re.compile(r"(?<![A-Za-z0-9_.-])eyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]{10,}){2}(?:\.[A-Za-z0-9_-]+){0,2}(?![A-Za-z0-9_-])"),
    # Discord bot token
    re.compile(r"(?<![A-Za-z0-9_.-])[MNO][A-Za-z0-9_-]{22,27}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,40}(?![A-Za-z0-9_-])"),
    # crypto wallet private key: 0x + 64 hex (an address is 40 hex and is left alone)
    re.compile(r"\b0x[0-9a-fA-F]{64}\b"),
)


def _extras():
    """Literal values from .claude/state/secret_extras.txt (not regexes); [] if unreadable or a symlink."""
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    path = os.path.join(root, ".claude", "state", "secret_extras.txt")
    try:
        if os.path.islink(path) or os.path.getsize(path) > 64 * 1024:
            return []
        with open(path, encoding="utf-8") as f:
            return sorted({s.strip() for s in f if len(s.strip()) >= 4 and not s.lstrip().startswith("#")},
                          key=len, reverse=True)
    except OSError:
        return []


def scrub(text: str) -> str:
    """Replaces secrets with LABEL. On any internal error it hides the WHOLE text (the safe side)."""
    if not text:
        return text
    try:
        for value in _extras():
            text = text.replace(value, LABEL)
        for p in PATTERNS:
            text = p.sub(LABEL, text)
        return text
    except Exception:
        return LABEL


if __name__ == "__main__":
    sys.stdout.write(scrub(sys.stdin.read()))
