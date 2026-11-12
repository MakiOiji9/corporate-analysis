#!/usr/bin/env bash
# Periodic commit & push while Claude runs, so a run stopped by the usage limit or the timeout keeps its work.
# Usage (run-claude.sh starts it in the background when AUTOSAVE_BRANCH is set, and stops it with TERM):
#   AUTOSAVE_BRANCH=analysis/issue-1 PUSH_TOKEN=... autosave.sh "<commit message>"
#
# Every AUTOSAVE_INTERVAL seconds (default 300) it runs commit-outputs.sh against AUTOSAVE_BRANCH (the same path
# checks; a failed save is logged and the loop goes on). A TERM waits for a save in progress, then exits.
set -uo pipefail

message="$1"
interval="${AUTOSAVE_INTERVAL:-300}"
here="$(cd "$(dirname "$0")" && pwd)"
stop=0
trap 'stop=1' TERM INT

while [ "$stop" -eq 0 ]; do
  sleep "$interval" &
  wait $! 2>/dev/null
  [ "$stop" -eq 1 ] && break
  BRANCH="$AUTOSAVE_BRANCH" NO_SUMMARY=1 bash "$here/commit-outputs.sh" "$message（途中保存 $(date +%H:%M)）" \
    || echo "::warning::途中保存に失敗した（次の周期でやり直す）"
done
