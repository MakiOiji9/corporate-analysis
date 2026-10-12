# tools/ — 情報収集スクリプト

スキル `collect-company-info`（`.ai/skills/collect-company-info.md`）と `collect-market-info`（`.ai/skills/collect-market-info.md`）から呼び出す Python スクリプト群。
設定はすべてこのリポジトリ内で完結し、ユーザー環境（`~/.claude` 等）には依存しない。

## 初回セットアップ（環境ごとに1回）

```powershell
pwsh tools/setup.ps1      # Windows
sh tools/setup.sh         # macOS / Linux / Git Bash
```

1. リポジトリ直下に `.venv` を作り、`tools/requirements.txt` をインストールする
2. `.env` が無ければ `.env.example` からコピーする → 必要なら次のキーを記入する（どちらも無料）
   - `EDINET_API_KEY`: 有報の XBRL 取得（[EDINET API の利用登録](https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1)）
   - `FRED_API_KEY`: 米国のマクロ指標（[FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html)）。未設定でも日本の時系列と米国の文書・CFTC は取れる
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

### 地合い用（`tools/collect/market/`）

入口は `market_collect.py` だけ。収集対象は `catalog/{japan,us}.json` で定義する（書き方は `.ai/templates/collect-market-info/source-access.md`）。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `market_collect.py prepare --market both --topic weekly` | 台帳の整合、時系列の取得（`--mode auto` が既定: 初回 10 年・以降 3 年）、新しい政策文書の検出・保存・抜粋・公表日の本文照合、確定日程の取得、要旨の骨組みと tasks.json（要旨化は 1〜3 文書ずつ束ねる）の作成 | `market/data/`、`market/policy/`、`market/sessions/…/` |
| `market_collect.py finalize --session market/sessions/…` | テンプレートとの照合、公表日の確認結果の反映、policy-digest・status（要確認事項つき）・`market/LATEST.md` の作成、範囲外の変更の検出 | 1行の JSON |
| `market_collect.py validate / abort --session …` | 検証だけ / 実行中の印を外し status を「中断」にする | 1行の JSON |
| `market_collect.py reopen --raw market/policy/…/raw/….md` | 完成済みの要旨を骨組みに戻し、抜粋を作り直す（ユーザーの指示があるときだけ） | 1行の JSON |
| `market_collect.py fix-date --raw market/policy/…/raw/….md [--date YYYY-MM-DD]` | 公表日の不一致を承認し、台帳と要旨ヘッダーの公表日を更新する（`--date` 省略時は要旨の「公表日（本文で確認）」） | 1行の JSON |
| `market_collect.py check-watch --market japan` | catalog の監視設定と確定日程の取得を試す（保存しない） | 標準出力 |
| `market_collect.py search boj --db CO --word 業況` / `search dashboard --word 失業率` | 系列コードを探す | 標準出力 |

モジュール: `series.py`（取得・パース）、`store.py`（時系列 CSV と前回・前年比）、`watch.py`（新着検出）、`docs.py`（文書ライブラリ）、`excerpt.py`（抜粋）、`render.py`（テンプレート）、`validate.py`（書式検証）。

株価指数（日経平均・S&P500・NASDAQ総合）は FRED から取るため、`FRED_API_KEY` が無いと日本の日経平均も取得失敗になる（レポートでは「—」）。

### 地合いレポート用（`tools/report/`）

スキル `market-report`（`.ai/skills/market-report.md`）から呼び出す。入口は `market_report.py` だけ。出力はすべて `market/report/{週の月曜}_*`。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `market_report.py check [--week YYYY-MM-DD]` | 今週の収集があるか（LATEST.md の最新セッションの日付 ≥ 週の月曜）、収集が実行中か、この週の outlook.md の状態 | 1行の JSON |
| `market_report.py prepare [--week …] [--redo] [--allow-stale]` | 数値・チャート系列・日程・文書の要点を集め、執筆の材料と outlook.md の骨組み（FILL 欄）を作る。作成途中の outlook.md は残す | `{週}_facts.json`・`{週}_brief.md`・`{週}_outlook.md` |
| `market_report.py build [--week …]` | outlook.md を検証（構造・FILL・判断の語・禁止表現）し、単一 HTML を出力 | `{週}_market-report.html` |

モジュール: `state.py`（週・鮮度）、`facts.py`（数値・系列・日程の集計。`collect/market/store.py` を再利用）、`brief.py`（材料と骨組み）、`outlook.py`（検証。`collect/market/validate.py` を再利用）、`charts.py`（インライン SVG）、`slides.py`（HTML）。テンプレートは `.ai/templates/market-report/`。

### 企業分析用（`tools/analysis/`）

スキル `five-forces`（`.ai/skills/five-forces.md`）から呼び出す。入口は `five_forces.py` だけ。出力はすべて `companies/{ticker}_{name}/analysis/five-forces/{分析日}_*`。`--company` は銘柄コード・ディレクトリ名・社名の一部のどれでもよい。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `five_forces.py list` | `companies/` の企業と、ファイブフォース分析の状態（none / fresh / expired / triggered / draft） | 1行の JSON |
| `five_forces.py check --company X` | 結果が有効か（365日以内で、分析後に新しい有報・業界・競合の raw が無いか）、必須の材料が raw にあるか（無ければ担当の collect-* を返す）、地合い判断が35日以内か。`next` に次の作業 | 1行の JSON |
| `five_forces.py prepare --company X [--redo]` | raw から必要な節を抜き出して執筆の材料にし、数値で決まる基準（最大顧客比率・粗利率の最大低下）の判定候補と前回の評価を入れた骨組み（FILL 欄）を作る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_five-forces.md` |
| `five_forces.py build --company X [--date …]` | md を検証（構造・FILL・評価の語・判定候補/前回との差の理由・禁止表現）し、点数・合計・魅力度を書き込む | `{日付}_five-forces.json` |

モジュール: `ff_paths.py`（企業の解決・結果の鮮度・有効期間）、`ff_inputs.py`（raw の節の抽出・欠損の判定）、`ff_metrics.py`（判定候補の計算）、`ff_brief.py`（材料）、`ff_doc.py`（骨組み・検証・採点。`report/outlook.py` の禁止表現と `collect/market/validate.py` を再利用）。テンプレートは `.ai/templates/five-forces/`。

### 書き込みガード（`tools/guard/write_guard.py`）

`.claude/settings.json` の PreToolUse hook として、Write / Edit の前に毎回実行される（標準ライブラリだけで動く。PATH 上の `python` を使う）。

- スクリプト専用のファイル（`data/`・`sources/`・`index.csv`・`tasks.json`・`status.md`・生成された表）の手書きをブロック
- `market/**/raw/*.md` は FILL 欄が残っている間だけ Edit を許可。`companies/*/raw/` の過去日付のファイルは変更禁止
- collect-market-info の実行中（`market/sessions/*/.running`）は、tasks.json の `allowed_files` 以外への書き込みをブロック
- `market/report/` の facts.json・brief.md・HTML は手書き禁止。outlook.md は Edit のみ（新規作成・上書き不可）で、過去の週の完成済みのものは変更禁止
- `companies/*/analysis/five-forces/` の brief.md・json は手書き禁止。five-forces.md は Edit のみで、過去の日付の build 済み（json がある）ものは変更禁止

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
.\.venv\Scripts\python.exe -m pytest tools/collect/tests tools/report/tests tools/analysis/tests -q
```
