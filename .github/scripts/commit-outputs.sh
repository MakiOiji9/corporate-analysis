#!/usr/bin/env bash
# Commit what a scheduled run produced and push it to main.
# Usage: commit-outputs.sh "<commit message>"
#
# Only companies/** and market/** may change. Anything else (code, workflows, settings, .env, the favorites
# ledger) stops the run without committing: the agent reads web pages, and an instruction planted in one must
# not reach main. The push token (PUSH_TOKEN) is given to this step only; checkout keeps no credentials.
set -euo pipefail

message="$1"
: "${PUSH_TOKEN:?PUSH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
remote="https://x-access-token:${PUSH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
max_attempts=3

changed="$(git -c core.quotepath=off status --porcelain=v1 --untracked-files=all | cut -c4-)"
if [ -z "$changed" ]; then
  echo "変更なし。コミットしない"
  exit 0
fi

forbidden="$(printf '%s\n' "$changed" | sed 's/^"//; s/"$//; s/^.* -> //' \
  | grep -Ev '^(companies|market)/' || true)"
ledger="$(printf '%s\n' "$changed" | grep -E '^companies/favorites\.json$' || true)"
if [ -n "$forbidden" ] || [ -n "$ledger" ]; then
  echo "::error::許可されていないパスが変更された。コミットしない:"
  printf '%s\n' "$forbidden" "$ledger" | sed '/^$/d'
  {
    echo "### コミットを中止した"
    echo "companies/・market/ 以外（または お気に入り台帳）が変更された:"
    printf '%s\n' "$forbidden" "$ledger" | sed '/^$/d; s/^/- /'
  } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  exit 1
fi

git add -A -- companies market
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit --quiet -m "$message"

for attempt in $(seq 1 "$max_attempts"); do
  if git push --quiet "$remote" HEAD:main; then
    echo "push 済み: $(git rev-parse --short HEAD) $message"
    echo "- コミット: \`$(git rev-parse --short HEAD)\` $message" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
    exit 0
  fi
  echo "push に失敗（${attempt}/${max_attempts}）。main を取り込み直す"
  if ! git -c user.name="github-actions[bot]" \
      -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
      pull --quiet --rebase "$remote" main; then
    git rebase --abort 2>/dev/null || true
    break # a conflict with a newer main: keep the commit on its own branch below
  fi
done

# Not on main: keep the output on a branch so it is not lost with the runner (merge it by hand).
rescue="auto/rescue-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%H%M%S)"
if git push --quiet "$remote" "HEAD:refs/heads/${rescue}"; then
  echo "::error::main に push できなかった（競合またはブランチ保護）。出力はブランチ ${rescue} に退避した"
  echo "- **main に push できなかった。** 出力はブランチ \`${rescue}\` に退避（手でマージする）" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
else
  echo "::error::main への push にも退避ブランチの push にも失敗した"
fi
exit 1
