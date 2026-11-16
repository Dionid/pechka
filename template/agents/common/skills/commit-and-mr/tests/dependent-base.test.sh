#!/usr/bin/env bash
#
# Dependent PR: `wt new --base <branch of an open PR>` forks the task from that
# branch and records it as the PR target; commit-and-mr opens the PR into it.
#   - wt new --base feature-x      -> recorded, PR opened into feature-x
#   - run.sh --base <b>            -> explicit override beats the record
#   - no --base                    -> default base, nothing recorded
#   - --base equal to the repo base, or to the task branch itself (adopt.sh
#     passes the adopted branch) -> nothing recorded, no self-target
#   - recorded base gone on origin -> default base, with a note
# git push and ls-remote are stubbed (no network); gh is tests/fake-gh.

set -euo pipefail
export GITHUB_TOKEN=fixture
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.test
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.test
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1
unset WORKSPACE_OWNER AGENT_SESSION_ID

skill="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$skill/../../../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

failures=0
check() {
  if [[ "$2" == "$3" ]]; then printf '  ok   %s\n' "$1"
  else printf '  FAIL %s\n    expected: %q\n    actual:   %q\n' "$1" "$2" "$3"; failures=$((failures + 1)); fi
}
g() { git -C "$1" "${@:2}" >/dev/null 2>&1; }
commit() { printf '%s\n' "$2" > "$1/$2"; g "$1" add "$2"; g "$1" commit -m "$2"; }

WS="$TMP/workspace"
mkdir -p "$WS/agents/common/skills/"{wt,commit-and-mr,clone} "$WS/packages" "$TMP/bin"
cp "$ROOT/agents/common/skills/wt/wt" "$WS/agents/common/skills/wt/wt"
cp "$skill/"{lib.sh,env.py,redact.py} "$WS/agents/common/skills/commit-and-mr/"
printf '#!/usr/bin/env bash\nexit 0\n' > "$WS/agents/common/skills/clone/ensure-repository"
chmod +x "$WS/agents/common/skills/clone/ensure-repository"
printf '{"branchPrefix":"feature/"}\n' > "$WS/harness.json"
printf '{"repos": {"app": {"branch": "main", "deps": "none"}}}\n' > "$WS/repos.json"
git init --quiet "$WS"

git init --quiet --bare -b main "$TMP/origin.git"
git init --quiet -b main "$TMP/seed"
commit "$TMP/seed" base
g "$TMP/seed" remote add origin "$TMP/origin.git"
g "$TMP/seed" push origin main
g "$TMP/seed" switch -c feature-x
commit "$TMP/seed" parent-work
g "$TMP/seed" push origin feature-x
git clone --quiet "$TMP/origin.git" "$WS/packages/app"
wt() { (cd "$WS" && bash agents/common/skills/wt/wt "$@"); }

# git shim: push succeeds; ls-remote answers from $TMP/remote-branches.
real_git="$(command -v git)"
cat > "$TMP/bin/git" <<SHIM
#!/usr/bin/env bash
for arg in "\$@"; do
  if [[ "\$arg" == push ]]; then printf 'pushed\n'; exit 0; fi
  if [[ "\$arg" == ls-remote ]]; then
    ref="\${@: -1}"; ref="\${ref#refs/heads/}"
    if grep -qx -- "\$ref" "$TMP/remote-branches"; then printf 'abc\trefs/heads/%s\n' "\$ref"; fi
    exit 0
  fi
done
exec "$real_git" "\$@"
SHIM
chmod +x "$TMP/bin/git"
ln -s "$skill/tests/fake-gh" "$TMP/bin/gh"
printf 'main\nfeature-x\n' > "$TMP/remote-branches"
mkdir -p "$TMP/gh-state"
export FAKE_GH_STATE="$TMP/gh-state"

cat > "$TMP/description" <<'EOD'
## Что и зачем

Проверить зависимый PR.

## Изменения

- Тест.

## Инфраструктура, схема, зависимости

Нет.

## Как проверить

Запустить dependent-base.test.sh.

## Риски и что осталось

Нет.

## Changelog

Нет.
EOD

# open_pr <task> [run.sh flags...] — commit in the task worktree and open the PR;
# prints "<base> <stderr-has-note>".
open_pr() {
  local task="$1" co="$WS/worktrees/$1/app"; shift
  # The checkout must look like a GitHub clone to run.sh; the shim handles push.
  git -C "$co" remote set-url origin git@github.com:group/app.git
  printf '%s\n' "$task" >> "$co/file-$task"
  printf 'test: %s\n' "$task" > "$TMP/msg"
  (cd "$WS" && WORKSPACE_COORDINATION_ROOT="$WS" PATH="$TMP/bin:$PATH" \
    bash "$skill/run.sh" --worktree "$co" --repo app --message-file "$TMP/msg" \
    --mr-description-file "$TMP/description" --no-task-link --no-spec-link "$@" -- "file-$task" 2>"$TMP/err" >"$TMP/out")
  git -C "$co" remote set-url origin "$TMP/origin.git"
  jq -r --arg b "feature/$task" '[.[] | select(.headRefName == $b)] | last | .baseRefName' "$TMP/gh-state/mrs.json"
}
rec() { git -C "$WS/packages/app" config --local --get "branch.feature/$1.workspaceBase" || echo none; }

# 1. dependent PR: forks from feature-x, records it, PR goes into it.
out="$(wt new d1 --repo app --base feature-x --allow-stale 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
check "wt new --base forks from the PR branch" "$(git -C "$TMP/seed" rev-parse feature-x)" "$(git -C "$WS/worktrees/d1/app" rev-parse HEAD)"
check "wt new --base records the PR target" feature-x "$(rec d1)"
check "PR is opened into the recorded base" feature-x "$(open_pr d1)"
check "reported TARGET_BRANCH" "TARGET_BRANCH=feature-x" "$(grep '^TARGET_BRANCH=' "$TMP/out" || true)"

# 2. explicit --base overrides the record.
out="$(wt new d2 --repo app --base feature-x --allow-stale 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
check "--base flag overrides the recorded base" main "$(open_pr d2 --base main)"

# 3. default unchanged: nothing recorded, PR into main.
out="$(wt new d3 --repo app --allow-stale 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
check "no --base: nothing recorded" none "$(rec d3)"
check "no --base: PR into the default base" main "$(open_pr d3)"

# 4. --base equal to the repo base records nothing.
out="$(wt new d4 --repo app --base main --allow-stale 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
check "--base <repo base> records nothing" none "$(rec d4)"

# 5. adopt-style: --base is the task branch itself — no self-target.
g "$TMP/seed" switch -q main
g "$TMP/seed" switch -q -c feature/d5
commit "$TMP/seed" d5-work
g "$TMP/seed" push origin feature/d5
g "$WS/packages/app" fetch origin
out="$(wt new d5 --repo app --base feature/d5 --allow-stale --no-always 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
check "adopt-style --base <own branch> records nothing" none "$(rec d5)"
printf 'main\nfeature-x\nfeature/d5\n' > "$TMP/remote-branches"
check "adopted branch targets the default base, not itself" main "$(open_pr d5)"

# 6. recorded base gone from origin: default base and a note.
out="$(wt new d6 --repo app --base feature-x --allow-stale 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
printf 'main\n' > "$TMP/remote-branches"
check "recorded base gone: default base" main "$(open_pr d6)"
check "recorded base gone: note printed" yes "$(grep -q "is gone from origin" "$TMP/err" && echo yes || echo no)"

# 7. an "always" repo in the run: it must not get the PR branch recorded, and
# the documented recipe uses --no-always.
git clone --quiet "$TMP/origin.git" "$WS/packages/spec"
printf '{"always":["spec"],"repos": {"app": {"branch": "main", "deps": "none"}, "spec": {"branch": "main", "deps": "none"}}}\n' > "$WS/repos.json"
printf 'main\nfeature-x\n' > "$TMP/remote-branches"
out="$(wt new d7 --repo app --base feature-x --allow-stale --no-always 2>&1)" || { printf '%s\n' "$out" >&2; exit 1; }
check "--no-always: recorded for the named repo" feature-x "$(rec d7)"
check "--no-always: spec repo not part of the run" no "$([ -d "$WS/worktrees/d7/spec" ] && echo yes || echo no)"
out="$(wt new d8 --repo app --base feature-x --allow-stale 2>&1)" || true
check "always repo never records the PR branch" none "$(git -C "$WS/packages/spec" config --local --get "branch.feature/d8.workspaceBase" || echo none)"

if ((failures)); then printf 'dependent-base: %d failure(s)\n' "$failures"; exit 1; fi
echo 'dependent-base: OK'
