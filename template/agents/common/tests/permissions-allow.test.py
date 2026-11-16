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
    # `find *` is not allowed: `*` spans spaces, so it would also approve
    # `find . -exec rm`; find goes to the auto-mode classifier instead.
    ("find . -name x", "prompt"),
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
    # sed is not allowed at all, so in-place edits need no ask rule.
    ("sed -i s/a/b/ f", "prompt"),
    ("sed -n -i p f", "prompt"),
    ("find -delete", "ask"),
    ("find . -delete", "ask"),
    ("find . -exec rm {} ;", "prompt"),
    ("find . -ok rm {} ;", "prompt"),
    ("find . -name x -fprint out", "ask"),
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
    ("./.claude/skills/banka-deploy/x.sh status", "ask"),
    ("python3 .claude/skills/banka-deploy/x.py", "ask"),
    (".claude/skills/x/../../../bin/rm -rf y", "ask"),
    ("node ../.yarn/releases/yarn-1/../../evil.js", "ask"),
    ("node -e evil", "ask"),
    ("node --eval=evil", "ask"),
    ("node -p evil", "ask"),
    ("node -pe evil", "ask"),
    ("node --print evil", "ask"),
    ("node --test -e evil", "ask"),
    ("node --test --eval evil", "ask"),
    ("node --test -pe evil", "ask"),
    ("node --test -e'x'", "ask"),
    ("node --test -r ./evil.js x.test.js", "ask"),
    ("node --test --require ./evil.js", "ask"),
    ("node --test --import=./evil.mjs", "ask"),
    ("node --test --loader ./evil.mjs", "ask"),
    ("node --test --experimental-loader=./evil.mjs", "ask"),
    ("node --test-only -e evil", "ask"),
    ("node -e'x'", "ask"),
    ("node -pe'x'", "ask"),
    ("./deploy.sh prod", "ask"),
    ("./scripts/deploy.sh prod", "ask"),
    ("bash scripts/deploy.sh", "ask"),
    ("npm run banka -- deploy", "ask"),
    # Former false positives of `*deploy*`, `node *-e*` and `*..*`.
    ("cat .claude/skills/banka-deploy/SKILL.md", "allow"),
    ("rg deploy .claude/skills", "allow"),
    ("cat scripts/deploy.sh", "allow"),
    ("node --test --test-reporter dot x.test.js", "allow"),
    ("node --test --experimental-x x.test.js", "allow"),
    ("node --test", "allow"),
    ("node --test tests/", "allow"),
    ("node --test --test-reporter=spec a.test.mjs", "allow"),
    ("node scripts/x.js --reporter dot", "prompt"),
    (".claude/skills/wt/wt new a --repo ../x", "allow"),
    (".claude/skills/wt/wt new a --repo x --pull ..", "allow"),
    ("node .yarn/releases/yarn-4.18.1.cjs test ../x", "allow"),
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
    ("npm run build:deploy", "ask"),
    ("npm run test:deploy", "ask"),
    ("npm run build -- deploy", "ask"),
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
