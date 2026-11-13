#!/usr/bin/env bash
# Run /company-report until today's report is built, one Claude run at a time, committing after each run.
# Usage: [BRANCH=analysis/issue-1] run-company-report.sh <company dir> "<label>" [<result json path>]
#
# A headless run often ends after the first analysis skill it calls (that skill's completion report reads as the
# end of the turn), so this loop calls the command again until company_report.py check says report_existing.
# Analyses that are fresh are skipped by the command itself, so every round goes on from where the last one
# stopped. A round that leaves `next` unchanged (usage limit, a skill stopped to ask) ends the loop as a failure.
# Needs CLAUDE_CODE_OAUTH_TOKEN and PUSH_TOKEN (each round is committed and pushed: BRANCH, default main).
set -uo pipefail

dir="$1"
label="$2"
out="${3:-${RUNNER_TEMP:-/tmp}/report.json}"
here="$(cd "$(dirname "$0")" && pwd)"
max_rounds="${MAX_ROUNDS:-15}"

next_step() {
  .venv/bin/python -I tools/report/company_report.py check --company "$dir" 2>/dev/null \
    | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("next", ""))' 2>/dev/null
}

prev=""
for round in $(seq 1 "$max_rounds"); do
  next="$(next_step)"
  echo "company_report check: next=${next:-（不明）}（${round} 回目）"
  if [ "$next" = "report_existing" ]; then
    echo "- ${label}: レポート作成済み（${round} 回目の確認）" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
    exit 0
  fi
  if [ -n "$prev" ] && [ "$next" = "$prev" ]; then
    echo "::error::${dir}: 前の実行で進まなかった（check の next: ${next}）。利用枠の上限か、スキルが確認待ちで止まった"
    exit 1
  fi
  status=0
  bash "$here/run-claude.sh" "/company-report $dir" "${label}（${round} 回目・next: ${next}）" "$out" || status=$?
  bash "$here/commit-outputs.sh" "chore: ${dir} の企業分析（${next}・自動実行 $(date +%F)）" \
    || echo "::warning::${dir}: コミットに失敗した"
  [ "$status" -eq 0 ] || exit "$status"
  prev="$next"
done
echo "::error::${dir}: ${max_rounds} 回実行してもレポートができなかった"
exit 1
