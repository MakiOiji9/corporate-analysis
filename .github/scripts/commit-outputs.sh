#!/usr/bin/env bash
# Commit what a run produced and push it to main (or to BRANCH, e.g. the work branch of an Issue).
# Usage: [BRANCH=analysis/issue-1] [NO_SUMMARY=1] commit-outputs.sh "<commit message>"
#
# Only companies/** and market/** may change. Anything else (code, workflows, settings, .env, the favorites
# ledger) stops the run without committing: the agent reads web pages, and an instruction planted in one must
# not reach the repository. The push token (PUSH_TOKEN) is given to this step only; checkout keeps no
# credentials. NO_SUMMARY=1 keeps the job summary quiet (the periodic autosave).
set -euo pipefail

message="$1"
: "${PUSH_TOKEN:?PUSH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
branch="${BRANCH:-main}"
remote="https://x-access-token:${PUSH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
max_attempts=3
summary="${GITHUB_STEP_SUMMARY:-/dev/null}"
[ "${NO_SUMMARY:-}" = "1" ] && summary=/dev/null

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
  } >> "$summary"
  exit 1
fi

git add -A -- companies market
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit --quiet -m "$message"

for attempt in $(seq 1 "$max_attempts"); do
  if git push --quiet "$remote" "HEAD:refs/heads/${branch}"; then
    echo "push 済み（${branch}）: $(git rev-parse --short HEAD) $message"
    echo "- コミット（${branch}）: \`$(git rev-parse --short HEAD)\` $message" >> "$summary"
    exit 0
  fi
  echo "push に失敗（${attempt}/${max_attempts}）。${branch} を取り込み直す"
  if ! git -c user.name="github-actions[bot]" \
      -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
      pull --quiet --rebase "$remote" "$branch"; then
    git rebase --abort 2>/dev/null || true
    break # a conflict with a newer branch head: keep the commit on its own branch below
  fi
done

# Not pushed: keep the output on a branch so it is not lost with the runner (merge it by hand).
rescue="auto/rescue-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$(date +%H%M%S)"
if git push --quiet "$remote" "HEAD:refs/heads/${rescue}"; then
  echo "::error::${branch} に push できなかった（競合またはブランチ保護）。出力はブランチ ${rescue} に退避した"
  echo "- **${branch} に push できなかった。** 出力はブランチ \`${rescue}\` に退避（手でマージする）" >> "$summary"
else
  echo "::error::${branch} への push にも退避ブランチの push にも失敗した"
fi
exit 1
