#!/usr/bin/env bash
# Run one Claude Code command headless and put its completion report into the job summary.
# Usage: run-claude.sh "<prompt, e.g. /market-report>" "<label for the summary>"
#
# Needs CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) in the environment of this step only.
# The conversation itself is not kept: only the final report goes to the summary, because artifacts are not
# masked the way logs are.
set -euo pipefail

prompt="$1"
label="$2"
out="${RUNNER_TEMP:-/tmp}/claude-result.json"
err="${RUNNER_TEMP:-/tmp}/claude-stderr.txt"

if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "::error::CLAUDE_CODE_OAUTH_TOKEN が無い。Environment 'reports' の Secret に登録する（tools/README.md の GitHub Actions の節）"
  exit 1
fi

status=0
claude -p "$prompt" \
  --settings .github/claude/ci-settings.json \
  --setting-sources project \
  --permission-mode dontAsk \
  --output-format json >"$out" 2>"$err" || status=$?

# The one JSON object of --output-format json: {"type":"result","is_error":..,"result":"..",...}
python3 -I - "$out" "$err" "$label" "$status" <<'PY'
import json, os, sys
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
lines = [f"## {label}", ""]
if len(denials) >= DENIAL_LIMIT:
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
sys.exit(1 if failed else 0)
PY
