#!/usr/bin/env python3
"""Self-test for permissions.allow in settings.base.json.

Allow rules exist so users stop clicking "Always allow" in every session. The
risk is the opposite: a prefix pattern that also swallows a mutating command.
Each command below is resolved the way Claude Code does it (deny > ask > allow; "prompt" = no rule, Claude Code asks;
`*` is a wildcard) and must land in the stated bucket.

    python3 agents/common/tests/permissions-allow.test.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SETTINGS = json.loads((Path(__file__).parents[2] / "claude" / "settings.base.json").read_text())
ALLOW = SETTINGS["permissions"]["allow"]
DENY = SETTINGS["permissions"]["deny"]
ASK = SETTINGS["permissions"]["ask"]


# `X` and `X *` are separate rules: `*` is a plain wildcard, so `X*` also matches
# `X-evil`, while `X *` needs a space. Rules below use the exact form where it matters.
def matches(rule: str, command: str) -> bool:
    if not (rule.startswith("Bash(") and rule.endswith(")")):
        return False
    pattern = re.escape(rule[5:-1]).replace(r"\*", ".*")
    return re.fullmatch(pattern, command, re.S) is not None


def verdict(command: str) -> str:
    if any(matches(r, command) for r in DENY):
        return "deny"
    if any(matches(r, command) for r in ASK):
        return "ask"
    if any(matches(r, command) for r in ALLOW):
        return "allow"
    return "prompt"


CASES = [
    ("git status --short", "allow"),
    ("git status", "allow"),
    ("git diff", "allow"),
    ("git log --oneline", "allow"),
    ("git branch --show-current", "allow"),
    ("git worktree list", "allow"),
    ("find . -name x", "allow"),
    ("yarn install", "allow"),
    ("node .yarn/releases/yarn-4.18.1.cjs lint", "allow"),
    ("node ../../.yarn/releases/yarn-4.18.1.cjs typecheck", "allow"),
    ("npx tsc --noEmit", "allow"),
    ("npm run build", "allow"),
    ("docker compose -p a-b up -d", "allow"),
    ("docker compose down", "allow"),
    ("gh pr view 12", "allow"),
    (".claude/skills/wt/wt new x --repo y --pull", "allow"),
    (".claude/skills/commit-and-mr/run.sh --worktree x", "allow"),
    ("sed -i s/a/b/ f", "ask"),
    ("sed -n -i p f", "ask"),
    ("find -delete", "ask"),
    ("find . -delete", "ask"),
    ("find . -exec rm {} ;", "ask"),
    ("find . -fls out", "ask"),
    ("rg --pre sh x .", "ask"),
    ("git diff --output=/tmp/x", "ask"),
    ("git log --output=/tmp/x", "ask"),
    ("git fetch origin +main:other", "ask"),
    ("docker compose down -v", "ask"),
    ("docker compose -p a down -v", "ask"),
    ("docker compose down --volumes", "ask"),
    ("node -e evil /a/.yarn/releases/y", "ask"),
    ("node .yarn/releases/../../evil.js", "ask"),
    (".claude/skills/../../../bin/rm -rf x", "ask"),
    (".claude/skills/banka-deploy/x.sh", "ask"),
    ("git branch -v -D main", "prompt"),
    ("git branch -vD main", "prompt"),
    ("git branch -r -d origin/x", "prompt"),
    ("git branch -D x", "prompt"),
    ("git difftool -x x", "prompt"),
    ("yarn node -e x", "prompt"),
    ("yarn exec rm x", "prompt"),
    ("yarn npm publish", "prompt"),
    ("yarn dlx cowsay", "prompt"),
    ("npm run deploy", "ask"),
    ("npx tsc-evil", "prompt"),
    ("git -C x push", "prompt"),
    ("git push origin x", "prompt"),
    ("git commit -m x", "prompt"),
    ("python3 -c print(1)", "prompt"),
    ("bash -c ls", "prompt"),
    ("gh pr merge 1", "prompt"),
    ("gh api -X POST /x", "prompt"),
    ("rm file", "prompt"),
    ("docker rm x", "prompt"),
]

bad = [(c, want, verdict(c)) for c, want in CASES if verdict(c) != want]
assert not bad, f"unexpected verdicts (command, wanted, got): {bad}"
assert "Edit(/worktrees/**)" in ALLOW
assert not any(r in DENY for r in ASK), "ask rules must not be duplicated in deny"
print(f"ok: {len(CASES)} permission cases")
