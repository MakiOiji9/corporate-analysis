# tools/ — 情報収集スクリプト

スキル `collect-company-info`（`.ai/skills/collect-company-info.md`）から呼び出す Python スクリプト群。
設定はすべてこのリポジトリ内で完結し、ユーザー環境（`~/.claude` 等）には依存しない。

## 初回セットアップ（環境ごとに1回）

```powershell
pwsh tools/setup.ps1      # Windows
sh tools/setup.sh         # macOS / Linux / Git Bash
```

1. リポジトリ直下に `.venv` を作り、`tools/requirements.txt` をインストールする
2. `.env` が無ければ `.env.example` からコピーする → 必要なら `EDINET_API_KEY` を記入する（[EDINET API の利用登録](https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1)、無料）
3. 最後に `preflight.py` が走り、使える取得経路を表示する

`.venv/`・`.env`・`.cache/`・`companies/*/sources/`（原本）は `.gitignore` 済み。

### Claude Code のフック設定（任意）

everything-claude-code プラグインの Fact-Forcing Gate（ファイル作成のたびに確認を求めるフック）を、このプロジェクトでは無効にする。
`.claude/settings.json` に以下を置く（プラグインが入っていない環境では何も起きない）。

```json
{
  "env": {
    "ECC_DISABLED_HOOKS": "pre:edit-write:gateguard-fact-force"
  }
}
```

## スクリプト

並列モード（collect-company-info の4担当がサブエージェントとして同時に動く）でも安全なように、共有ファイル（`sources/manifest.csv`、`data/*.csv`、`.cache/edinet/`）への書き込みはロック（`<file>.lock`）と一時ファイル→置き換えで保護している。共有ファイルは手で編集しないこと。

実行は `.venv` の Python で `python -I tools/collect/<script>.py ...`（Windows は `.venv\Scripts\python.exe`）。各スクリプトは `--help` で使い方を表示する。

| スクリプト | 用途 | 主な出力 |
|---|---|---|
| `preflight.py` | 環境・取得経路の事前チェック | 標準出力（表） |
| `fetch.py` | URL から原本を保存（sha256 で重複排除）、`--text` でテキスト化 | `sources/YYYY-MM-DD/`、`sources/manifest.csv` |
| `pdf_text.py` | PDF/HTML → ページ区切りテキスト | `<原本>.txt` |
| `find_pages.py` | テキストから表紙・見出し・財務行・任意パターンのページだけ抽出 | 標準出力 |
| `edinet.py` | EDINET API v2 の書類一覧・取得（要 `EDINET_API_KEY`） | `sources/`、`.cache/edinet/` |
| `xbrl_financials.py` | EDINET XBRL→CSV から財務を抽出 | `data/financials.csv` |
| `tdnet_summary.py` | 決算短信 iXBRL から実績・予想・配当・株式数を抽出 | `data/tdnet_facts.csv` |
| `render_tables.py` | data の CSV から Markdown 表を出力 | 標準出力 |

## 例（3798 ULSグループ）

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -I tools/collect/preflight.py
& $py -I tools/collect/fetch.py https://ssl4.eir-parts.net/doc/3798/yuho_pdf/S100YCBQ/00.pdf `
      --company 3798_uls-group --type yuho --period 2026-03 --doc-id S100YCBQ --text
& $py -I tools/collect/find_pages.py toc companies/3798_uls-group/sources/2026-10-11/S100YCBQ.pdf.txt
& $py -I tools/collect/tdnet_summary.py companies/3798_uls-group/sources/2026-10-11/140120260511523776.htm `
      --company 3798_uls-group --doc-id 140120260511523776
& $py -I tools/collect/render_tables.py forecasts 3798_uls-group
```

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest tools/collect/tests -q
```
