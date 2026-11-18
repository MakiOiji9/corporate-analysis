#!/usr/bin/env bash
# Run one Claude Code command headless and put its completion report into the job summary.
# Usage: run-claude.sh "<prompt, e.g. /market-report>" "<label for the summary>" [<result json path>]
#
# The result JSON ({"result": <completion report>, ...}) is kept at the third argument (default
# $RUNNER_TEMP/claude-result.json) so a later step can quote the report, e.g. in an Issue comment.
# Needs CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) in the environment of this step only.
# With AUTOSAVE_BRANCH (and PUSH_TOKEN) set, autosave.sh commits & pushes to that branch every few minutes while
# Claude runs. Claude itself is started without PUSH_TOKEN / GH_TOKEN / GITHUB_TOKEN in its environment.
# The conversation itself is not kept: only the final report goes to the summary, because artifacts are not
# masked the way logs are.
# MAX_TURNS (default 100) caps one run so a runaway round cannot use up the plan's usage by itself. A run cut
# by it exits with 3 (EXIT_MAX_TURNS), so a caller looping over rounds can go on instead of failing.
# ci_rules is appended to the system prompt: the Bash forms ci-settings.json denies, so Claude does not spend
# turns retrying them.
set -euo pipefail

prompt="$1"
label="$2"
out="${3:-${RUNNER_TEMP:-/tmp}/claude-result.json}"
err="${RUNNER_TEMP:-/tmp}/claude-stderr.txt"
max_turns="${MAX_TURNS:-100}"

ci_rules="$(cat <<'EOF'
# CI（GitHub Actions）での実行の制約
この実行はヘッドレスで、.github/claude/ci-settings.json の許可に合わないツール呼び出しは確認なしに拒否される。拒否されたコマンドを形を変えて試すとターンと利用枠を無駄にするので、最初から次の形を使う。
- ファイルを読む・探すときは Read・Grep・Glob ツールを使う。Bash で cat・head・tail・grep・sed・awk・wc を使わない
- Bash のコマンドにパイプ（|）・;・&&・$( )・バッククォートを含めない。sleep・timeout・env を前に付けない
- Python は `.venv/bin/python -I tools/analysis/...`・`tools/collect/...`・`tools/report/...` の形で直接呼ぶ。出力を絞りたいときもパイプは使わず、全文を受け取って読む
- 長い処理もバックグラウンドにせず前面で実行する（バックグラウンドの出力を sleep で待てない）
- 一度拒否された形のコマンドは繰り返さない
EOF
)"

if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "::error::CLAUDE_CODE_OAUTH_TOKEN が無い。Environment 'reports' の Secret に登録する（tools/README.md の GitHub Actions の節）"
  exit 1
fi

saver=""
if [ -n "${AUTOSAVE_BRANCH:-}" ]; then
  bash "$(dirname "$0")/autosave.sh" "chore: ${label}" &
  saver=$!
fi

status=0
env -u PUSH_TOKEN -u GH_TOKEN -u GITHUB_TOKEN claude -p "$prompt" \
  --settings .github/claude/ci-settings.json \
  --setting-sources project \
  --permission-mode dontAsk \
  --max-turns "$max_turns" \
  --append-system-prompt "$ci_rules" \
  --output-format json >"$out" 2>"$err" || status=$?

if [ -n "$saver" ]; then
  kill -TERM "$saver" 2>/dev/null || true
  wait "$saver" 2>/dev/null || true
fi

# The one JSON object of --output-format json: {"type":"result","is_error":..,"result":"..",...}
python3 -I - "$out" "$err" "$label" "$status" <<'PY'
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")  # the report can hold characters the console code page lacks
out, err, label, status = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
try:
    data = json.loads(open(out, encoding="utf-8").read() or "{}")
except ValueError:
    data = {}
stderr = open(err, encoding="utf-8", errors="replace").read()[-2000:]
text = data.get("result") or ""
denials = data.get("permission_denials") or []
DENIAL_LIMIT = 10  # many denials: the run could not work (ci-settings.json lacks a rule), even if Claude exited 0
failed = status != 0 or data.get("is_error") or not data or len(denials) >= DENIAL_LIMIT
auth = any(k in (text + stderr).lower() for k in ("oauth", "401", "authentication", "invalid api key", "unauthorized"))
usage = any(k in (text + stderr).lower() for k in ("out of extra usage", "usage limit", "limit reached", "rate limit"))
EXIT_MAX_TURNS = 3  # run-company-report.sh goes on to the next round on this code
max_turns = data.get("subtype") == "error_max_turns" and not usage
lines = [f"## {label}", ""]
if failed and usage:
    lines += ["**Claude の利用枠を使い切って止まった。** 下の完了報告にあるリセット時刻の後に、この実行の Re-run failed jobs で"
              "続きから進める（途中までの収集・分析はコミット済み）。定期実行の企業数を減らすか、プランの枠を見直す。", ""]
elif max_turns:
    lines += [f"**1回の実行のターン上限（MAX_TURNS={os.environ.get('MAX_TURNS', '100')}）に達して止まった。** "
              "途中までの分はコミットされ、続きは次の回で進める。何度も達するなら拒否されたツールを確かめるか、MAX_TURNS を上げる。", ""]
elif len(denials) >= DENIAL_LIMIT:
    lines += [f"**ツールの拒否が {len(denials)} 件あった。** `.github/claude/ci-settings.json` の許可に足りないものがある。", ""]
elif failed and auth:
    lines += ["**認証に失敗した。** トークンが期限切れ（1年）か失効している。ローカルで `claude setup-token` を実行し、"
              "Environment `reports` の Secret `CLAUDE_CODE_OAUTH_TOKEN` を更新する。", ""]
elif failed:
    lines += [f"**Claude Code が失敗した**（終了コード {status}、subtype {data.get('subtype')}）。", ""]
lines += [text or "（完了報告なし）", ""]
if denials:
    lines += [f"<details><summary>拒否されたツール（{len(denials)} 件）</summary>", ""]
    for d in denials[:30]:
        args = d.get("tool_input") or {}
        target = args.get("command") or args.get("file_path") or args.get("path") or args.get("pattern") or ""
        lines.append(f"- `{d.get('tool_name')}` {str(target)[:160]}")
    lines += ["", "</details>", ""]
if failed and stderr.strip():
    lines += ["<details><summary>stderr</summary>", "", "```", stderr.strip(), "```", "", "</details>", ""]
meta = {k: data.get(k) for k in ("num_turns", "duration_ms", "total_cost_usd") if data.get(k) is not None}
if meta:
    lines.append(f"<sub>{meta}</sub>")
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
print("\n".join(lines))
sys.exit(EXIT_MAX_TURNS if max_turns else 1 if failed else 0)
PY
