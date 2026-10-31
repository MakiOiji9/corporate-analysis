# tools/ — 情報収集スクリプト

スキル `collect-company-info`（`.ai/skills/collect-company-info.md`）と `collect-market-info`（`.ai/skills/collect-market-info.md`）から呼び出す Python スクリプト群。
設定はすべてこのリポジトリ内で完結し、ユーザー環境（`~/.claude` 等）には依存しない。

## 初回セットアップ（環境ごとに1回）

```powershell
pwsh tools/setup.ps1      # Windows
sh tools/setup.sh         # macOS / Linux / Git Bash
```

1. リポジトリ直下に `.venv` を作り、`tools/requirements.txt` をインストールする
2. `.env` が無ければ `.env.example` からコピーする → 必要なら次のキーを記入する（いずれも無料）
   - `EDINET_API_KEY`: 有報の XBRL 取得（[EDINET API の利用登録](https://api.edinet-fsa.go.jp/api/auth/index.aspx?mode=1)）
   - `FRED_API_KEY`: 米国のマクロ指標（[FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html)）。未設定でも日本の時系列と米国の文書・CFTC は取れる
   - `SEC_USER_AGENT`: 米国株の SEC EDGAR 取得（`fetch.py`・`edgar.py`）。登録は不要で、`名前 メールアドレス` の形式で書く（[SEC のアクセス規約](https://www.sec.gov/os/accessing-edgar-data)）。未設定だと sec.gov は 403 を返す
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
| `edgar.py` | SEC EDGAR の提出書類一覧（`list`）、companyfacts から年次財務を抽出（`facts`。米国株。要 `SEC_USER_AGENT`） | 標準出力、`data/financials.csv` |
| `render_tables.py` | data の CSV から Markdown 表を出力 | 標準出力 |
| `sources_admin.py` | manifest の誤登録行を除去（`remove`。原本は `sources/_removed/` へ移動） | `sources/manifest.csv` |

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
| `market_report.py prepare [--week …] [--redo] [--allow-stale]` | 数値・チャート系列・日程・文書の要点を集め、計算した指標・3つの軸の評価の候補・前週との食い違い・データの点検とともに、執筆の材料と outlook.md の骨組み（FILL 欄）を作る。作成途中の outlook.md は残す | `{週}_facts.json`・`{週}_brief.md`・`{週}_outlook.md` |
| `market_report.py build [--week …]` | outlook.md を検証（構造・FILL・判断の語・禁止表現に加え、候補を変えた理由、採用と1章の3軸・注意の度合いの一致、前回からの変更理由、引き継ぎと業種の表が facts.json と同じか、やさしい要約の個数と専門用語）し、単一 HTML（16枚）と判断の記録を出力 | `{週}_market-report.html`・`{週}_judgment.json` |
| `market_report.py backtest [--years 10]` | 過去の毎週金曜を、その日までに公表済みのデータだけで評価し直し、軸のラベルが意味どおりか（ストレス → その後の値動きの大きさ・大きな下落、金融環境 → 金利の変化、景気 → 失業率の変化）を前半・後半に分けて集計する | `market/report/backtest/{日付}_backtest.md`・`.json` |

モジュール: `state.py`（週・鮮度）、`facts.py`（数値・系列・日程の集計。`collect/market/store.py` を再利用）、`derived.py`（実質金利・長短金利差・移動平均からの乖離・HY スプレッドの位置・益利回りと10年債の差）、`scoring.py`（3つの軸の信号・しきい値・ヒステリシス・注意の度合い）、`consistency.py`（前週の facts.json との日程の食い違い）、`sanity.py`（データの妥当性の点検）、`sectors.py`（業種 ETF の騰落と指数との差）、`glossary.py`（初心者向けの用語集と判断の語の説明）、`backtest.py`（過去データでの検証）、`brief.py`（材料と骨組み）、`outlook.py`（検証。`collect/market/validate.py` を再利用）、`charts.py`（インライン SVG）、`slides.py`（HTML）。テンプレートは `.ai/templates/market-report/`。

### 企業分析レポート用（`tools/report/company_report.py`）

コマンド `company-report`（`.ai/prompts/company-report.md`、エントリーポイントは `.claude/commands/company-report.md`）から呼び出す。入口は `company_report.py` だけ。出力はすべて `companies/{ticker}_{name}/reports/{作成日}_company-report*`。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `company_report.py list` | `companies/` の企業と、鮮度が新しくない分析（`not_fresh`）・最新のレポートの日付と状態 | 1行の JSON |
| `company_report.py check --company X [--redo] [--use-existing]`（`--use-existing` は triggered の分析を作り直さず既存の結果を使う。prepare も同じ） | 9つの分析（five-forces → three-c → moat → swot → profitability → growth → safety → cash-flow → valuation。鮮度は各スクリプトの `evaluate()`）、地合い判断の古さ（35日）、今日のレポートの状態から `next`（最初の新しくない分析のスキル名 / market-report / prepare / write / build / report_existing） | 1行の JSON |
| `company_report.py prepare --company X [--redo] [--skip-prices] [--skip-market-report]` | 株価を取得し（`tools/collect/stock_prices.py`）、STEP 1・2 の総合判定（A/B/C）、判定マトリクス、短期・中期・長期の判定と条件表、株価のレンジ・移動平均を計算して facts.json に保存し、執筆の材料と md の骨組み（1章の判定の表はスクリプト、文章は FILL）を作る。作成途中の md は文章を残して判定の表だけを更新する | `{日付}_company-report_facts.json`・`_brief.md`・`.md` |
| `company_report.py build --company X [--date …]` | md を検証（構造・FILL・判定の表が facts.json と同じか・3行まとめと箇条書きの数・各期間の説明が判定語を含むか・禁止表現）し、単一 HTML（判定カード・根拠の表・STEP 1〜3・財務と株価のチャート・用語集）と要約の json を出力 | `{日付}_company-report.html`・`.json` |

モジュール: `cr_status.py`（9つの分析の鮮度と次の作業。各分析スクリプトの `evaluate()` を再利用）、`cr_judge.py`（STEP 1・2 の総合判定・判定マトリクス・3期間の判定。純関数）、`cr_prices.py`（株価のレンジ・移動平均・月次の系列・年ごとの高値と安値。prices.csv が無ければ raw の年次表）、`cr_facts.py`（分析結果・地合い・次回の見直し日の集約）、`cr_doc.py`（材料・骨組み・検証）、`cr_render.py`（HTML。`charts.py`・`slides.esc/table` を再利用）、`cr_glossary.py`（企業分析の用語集と判定語の説明）。テンプレートは `.ai/templates/company-report/`。

株価の取得は `tools/collect/stock_prices.py --company X [--years 10]`（Yahoo Finance のチャート API。非公式・キー不要。日本株は `{コード}.T`）。分割調整済みの日足を `companies/{ticker}_{name}/data/prices.csv`（`date,open,high,low,close,adj_close,volume,retrieved`）に保存する。

### 企業分析用（`tools/analysis/`）

スキル `five-forces`（`.ai/skills/five-forces.md`）から呼び出す。入口は `five_forces.py` だけ。出力はすべて `companies/{ticker}_{name}/analysis/five-forces/{分析日}_*`。`--company` は銘柄コード・ディレクトリ名・社名の一部のどれでもよい。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `five_forces.py list` | `companies/` の企業と、ファイブフォース分析の状態（none / fresh / expired / triggered / draft） | 1行の JSON |
| `five_forces.py check --company X` | 結果が有効か（365日以内で、分析後に新しい有報・業界・競合の raw が無いか）、必須の材料が raw にあるか（無ければ担当の collect-* を返す）、地合い判断の古さ（`outlook_stale`。参照だけなので次の作業は止めない）。`next` に次の作業 | 1行の JSON |
| `five_forces.py prepare --company X [--redo]` | raw から必要な節を抜き出して執筆の材料にし、数値で決まる基準（最大顧客比率と前期からの変化・粗利率の最大低下）の判定候補と前回の評価を入れた骨組み（FILL 欄）を作る。材料には自社の粗利率・営業利益率の時系列と、競合の営業利益率の推移（売上高・営業利益から計算）も入る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_five-forces.md` |
| `five_forces.py build --company X [--date …]` | md を検証（構造・FILL・評価の語・根拠の確度の語・評価が変わる条件・判定候補/前回との差の理由・禁止表現）し、点数・合計・魅力度を書き込む。「迷った:」の要因と確度が参考の要因を返す | `{日付}_five-forces.json` |

モジュール: `an_common.py`（企業の解決・日付つき結果ファイル・有効期間・地合いの参照。three-c と共有）、`ff_paths.py`（ファイブフォースの結果の場所と鮮度）、`ff_inputs.py`（raw の節の抽出・欠損の判定）、`ff_metrics.py`（判定候補の計算）、`ff_brief.py`（材料）、`ff_doc.py`（骨組み・検証・採点。`report/outlook.py` の禁止表現と `collect/market/validate.py` を再利用）。テンプレートは `.ai/templates/five-forces/`。

スキル `three-c`（`.ai/skills/three-c.md`）からは `three_c.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/three-c/{分析日}_*`。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `three_c.py list` | `companies/` の企業と、3C分析の状態（none / fresh / expired / triggered / draft）・結論・ファイブフォースの状態 | 1行の JSON |
| `three_c.py check --company X` | 結果が有効か（180日以内で、分析後に新しい有報・事業概要・業界・競合の raw や新しいファイブフォース分析が無いか）、ファイブフォースが有効か（無効なら `next: five_forces`）、必須の材料が raw にあるか（無ければ担当の collect-* を返す）、地合い判断の古さ（参照だけ）。`next` に次の作業 | 1行の JSON |
| `three_c.py prepare --company X [--redo]` | raw から必要な節を抜き出して執筆の材料にし、比較表（対象企業と競合最大5社の売上高・営業利益率・シェア・売上高3年CAGR）、成長性と競合との比較の判定候補、競合の凡例、前回の評価を入れた骨組み（FILL 欄）を作る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_three-c.md` |
| `three_c.py build --company X [--date …]` | md を検証（構造・FILL・評価の語・根拠の確度・KBF 表と1章の一致・○△×？の記号・判定候補/前回との差の理由・禁止表現）し、勝てる理由の結論（明確 / あいまい / なし / 判定保留）を判定して書き込む | `{日付}_three-c.json` |

モジュール: `tc_paths.py`（3C の結果の場所と鮮度）、`tc_inputs.py`（3C の入力一覧。抽出は `ff_inputs.py` を再利用）、`tc_metrics.py`（比較表・判定候補）、`tc_brief.py`（材料）、`tc_doc.py`（骨組み・検証・結論の判定）。テンプレートは `.ai/templates/three-c/`。

スキル `moat`（`.ai/skills/moat.md`）からは `moat.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/moat/{分析日}_*`。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `moat.py list` | `companies/` の企業と、モート分析の状態（none / fresh / expired / triggered / draft）・結論・3C分析の状態 | 1行の JSON |
| `moat.py check --company X` | 結果が有効か（180日以内で、分析後に新しい有報・財務時系列・事業概要・業界・競合の raw や新しい3C分析が無いか）、3Cが有効か（無効なら `next: three_c`。3Cの結論では止めない）、必須の材料が raw にあるか（無ければ担当の collect-* を返す）、地合い判断の古さ（参照だけ）。`next` に次の作業 | 1行の JSON |
| `moat.py prepare --company X [--redo]` | raw から必要な節を抜き出して執筆の材料にし、営業利益率の同業比較（自社の最大10年と競合最大5社の単純平均を決算期6か月以内で突き合わせ、連続で上回った年数から 強い/弱い/なし の判定候補）、コスト構造の表、3Cの結論、前回の判定を入れた骨組み（FILL 欄）を作る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_moat.md` |
| `moat.py build --company X [--date …]` | md を検証（構造・FILL・モート5種の行と判定の語・根拠の確度・シェアの推移・崩しうる要因の時期・前回との差の理由・禁止表現）し、数字の裏付け（強い / 弱い / なし / 不明）とモートの強さ（広い / 狭い / なし / 判定保留）を判定して書き込む。裏付けなしなら「該当」を「該当なし」に修正 | `{日付}_moat.json` |

モジュール: `mt_paths.py`（モートの結果の場所と鮮度）、`mt_inputs.py`（モートの入力一覧。抽出は `ff_inputs.py` を再利用）、`mt_metrics.py`（営業利益率の同業比較・判定候補・コスト構造）、`mt_brief.py`（材料）、`mt_doc.py`（骨組み・検証・結論の判定）。テンプレートは `.ai/templates/moat/`。

スキル `swot`（`.ai/skills/swot.md`）からは `swot.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/swot/{分析日}_*`。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `swot.py list` | `companies/` の企業と、SWOT分析の状態（none / fresh / expired / triggered / draft）・結論・モート分析の状態 | 1行の JSON |
| `swot.py check --company X` | 結果が有効か（180日以内で、分析後に有報・中期経営計画・事業概要・業界の使った節が変わっていないか、新しいファイブフォース・3C・モート分析が無いか）、モートが有効か（無効なら `next: moat`。上流の結論では止めない）、地合い（outlook.md）が35日以内か（古ければ `next: market_report`）、必須の材料が raw にあるか（無ければ担当の collect-* を返す）。`next` に次の作業 | 1行の JSON |
| `swot.py prepare --company X [--redo] [--skip-collect] [--skip-market-report]` | raw から必要な節と地合いの該当市場の行を抜き出して執筆の材料にし、上流3分析の結論、必ず記載する項目（ファイブフォースの「強」→ 脅威、残ったモート → 強み）、影響度の目安（直近の売上高・営業利益と 20%・5% の金額）、前回の判定を入れた骨組み（FILL 欄）を作る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_swot.md` |
| `swot.py build --company X [--date …]` | md を検証（構造・FILL・4象限の番号・由来・確度・影響度の語・必ず記載する項目・最大の強み/脅威が影響度の規則に合うか・判定と結論の文の形・前回との差の理由・禁止表現）し、SWOT の結論（Yes / 条件付き / No / 判定保留）を判定して書き込む | `{日付}_swot.json` |

モジュール: `sw_paths.py`（SWOT の結果の場所と鮮度）、`sw_inputs.py`（SWOT の入力一覧。抽出は `ff_inputs.py` を再利用）、`sw_metrics.py`（影響度の目安と、raw の表の金額を目安と比べた影響度の候補）、`sw_brief.py`（材料。上流3分析の json の結論と根拠・出典、outlook.md の抜粋を含む。同じ raw の節は1回だけ載せ、中計が無い会社の中計の節は「該当なし」にする）、`sw_doc.py`（骨組み・検証・結論の判定）。テンプレートは `.ai/templates/swot/`。

スキル `profitability`（`.ai/skills/profitability.md`、STEP 2-1 収益性）からは `profitability.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/profitability/{分析日}_*`。数値と判定はすべてスクリプトが出し、LLM は数値の背景だけを書く。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `profitability.py list` | `companies/` の企業と、収益性分析の状態（none / fresh / expired / triggered / draft）・結論・モートと3Cの結論 | 1行の JSON |
| `profitability.py check --company X` | 結果が有効か（180日以内で、使った節と年次の数値が変わっていないか、新しいモート・3C分析が無いか）、材料があるか（自社の財務時系列5年以上 → collect-filings、競合の「収益性の分解」と営業利益率の推移 → collect-peers-valuation）。STEP 1 は前提にしない。`next` に次の作業 | 1行の JSON |
| `profitability.py prepare --company X [--redo] [--skip-collect]` | 自社の年次系列（data/*.csv → 有報・財務時系列の表。単位 千円/百万円/億円 を判別、一次の値を優先）から ROE（期首期末平均の自己資本）・3要素を計算し、手順1〜3の判定（同業比較は 純利益率 ±1pt・回転率とレバレッジ ±5% 以内を同等とみなす）、営業利益率と3要素の同業比較、ROE が2pt以上動いた年の主因（営業利益率・特別損益の前年比つき）、特別損益の比率と除いた ROE・除いた場合の手順1、境界に近い比較、STEP 1 との整合性を入れた骨組み（FILL は背景だけ）と材料を作る。返り値に書く欄の一覧（`fill_keys`）。作成途中の md は残す | `{日付}_brief.md`・`{日付}_profitability.md` |
| `profitability.py build --company X [--date …]` | md を検証（構造・FILL・3.3 の年度がスクリプトの抽出と一致・必須欄・禁止表現）し、数値を raw から計算し直して収益性（良好 / 普通 / 懸念 / 判定保留）を書き込む | `{日付}_profitability.json` |

モジュール: `pf_paths.py`（結果の場所と鮮度）、`pf_inputs.py`（入力一覧。抽出は `ff_inputs.py` を再利用）、`pf_series.py`（自社・競合の年次系列: 売上高・当期純利益・総資産・自己資本・自己資本比率・ROE・特別損益。表の読み取り（単位の判別、△・括弧の負数、一次と二次の優先）は `Fields` で読む項目を差し替えて cash-flow も使う）、`pf_metrics.py`（ROE とデュポン分解、手順1〜4の判定、整合性チェック、収集の要求。営業利益率の同業比較は `mt_metrics.py` を再利用）、`pf_brief.py`（材料）、`pf_doc.py`（骨組み・検証・結論）。テンプレートは `.ai/templates/profitability/`。

スキル `cash-flow`（`.ai/skills/cash-flow.md`、STEP 2-4 キャッシュフロー分析）からは `cash_flow.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/cash-flow/{分析日}_*`。数値と判定はすべてスクリプトが出し、LLM は数値の背景だけを書く。同業比較は使わない。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `cash_flow.py list` | `companies/` の企業と、キャッシュフロー分析の状態（none / fresh / expired / triggered / draft）・結論・収益性・成長性・安全性の結論 | 1行の JSON |
| `cash_flow.py check --company X` | 結果が有効か（180日以内で、使った節と年次の数値が変わっていないか、新しい収益性・成長性・安全性分析が無いか）、材料があるか（自社の営業CF 5年以上・株主還元、手順3が懸念なら CF 計算書の営業活動の内訳 → collect-filings）。`next` に次の作業 | 1行の JSON |
| `cash_flow.py prepare --company X [--redo] [--skip-collect]` | 自社の年次系列（data/*.csv → 有報・財務時系列の表。配当は CF 計算書の支払額を優先し、短信の配当金総額は最後の補完）から FCF・営業CF対純利益比率（5年平均と累計の低い方）を計算し、手順1〜5の判定（一時要因・成長投資期は数値の代理指標）、純利益と営業CF の差の内訳（減価償却費・売上債権の増減・棚卸資産の増減・税金の支払いと計上の差）と主因、直近の推移と最も古い年を除いた平均、売上債権・棚卸資産と売上高の増加率、財務CF の中身で書き分けた年ごとの CF パターン、株主還元と FCF（0扱いは「0（記載なし）」）、境界に近い比較、収益性・成長性・安全性分析との関係を入れた骨組み（FILL は背景だけ）と材料を作る。返り値に書く欄の一覧（`fill_keys`）。作成途中の md は残す | `{日付}_brief.md`・`{日付}_cash-flow.md` |
| `cash_flow.py build --company X [--date …]` | md を検証（構造・FILL・必須欄・禁止表現、書いた欄の数値が md の表か brief にあるか、概数（約〜・〜割）が無いか）し、数値を raw から計算し直してキャッシュフロー（良好 / 普通 / 懸念 / 判定保留）を書き込む | `{日付}_cash-flow.json` |

モジュール: `cf_paths.py`（結果の場所と鮮度）、`cf_inputs.py`（入力一覧。抽出は `ff_inputs.py` を再利用）、`cf_series.py`（自社の年次系列: 営業・投資・財務CF・売上高・当期純利益・売上債権・棚卸資産・配当金の支払額・自己株式の取得・設備投資・子会社株式の取得、営業CF の内訳（税金等調整前当期純利益・減価償却費・売上債権と棚卸資産の増減額・法人税等の支払額）。表の読み取りは `pf_series.py` に CF 用の `Fields`（「増減」「税金等調整前」を除外しない）を渡す）、`cf_metrics.py`（手順1〜6の判定、差の内訳、STEP 2 の他の分析との関係、収集の要求）、`cf_brief.py`（材料）、`cf_doc.py`（骨組み・検証・結論）。成長性・安全性の結果は `gr_paths.py`・`sf_paths.py` で読む。テンプレートは `.ai/templates/cash-flow/`。

スキル `growth`（`.ai/skills/growth.md`、STEP 2-2 成長性）からは `growth.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/growth/{分析日}_*`。数値と判定はすべてスクリプトが出し、LLM は減収・減益の年の分類（一時 / 構造 / 不明）と数値の背景だけを書く。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `growth.py list` | `companies/` の企業と、成長性分析の状態（none / fresh / expired / triggered / draft）・結論・3C の市場の成長性・SWOT の結論 | 1行の JSON |
| `growth.py check --company X` | 結果が有効か（180日以内で、使った節と年次の数値が変わっていないか、新しい 3C・SWOT 分析が無いか）、材料があるか（自社の売上高・EPS 5年以上・会社計画と実績・M&A・連結範囲の変更・減収減益の年の会社説明 → collect-filings）。STEP 1 は前提にしない。`next` に次の作業。`missing_inputs` の各要求に `hints`（雛形の章名・`sources/` に保存済みの関連原本） | 1行の JSON |
| `growth.py prepare --company X [--redo] [--skip-collect]` | 自社の年次系列（短信 → data/*.csv → 有報・財務時系列の表。千円/百万円/億円/千米ドル、括弧の負数を判別、一次の値を優先）から CAGR（EPS は純利益÷EPS の株式数の整数倍の変化を株式分割とみなして調整）、手順1の判定、減収・減益の年と2年以内の回復、期初予想の達成率と手順3の判定（直近3年の平均達成率つき）、今期の進捗（短信の最新の四半期累計の前年同期比と通期予想に対する進捗率）、成長の質（営業利益と売上の CAGR を長期と直近3年で、M&A を除いた売上 CAGR、EPS と純利益の CAGR の差）、境界に近い比較と保守的判断（結論を左右する比較が 1pt 以内なら1段階下げる）、株式分割の記録（status.md・raw）との照合、3C の市場成長率との整合性を入れた骨組み（FILL は分類と背景だけ）と材料を作る。返り値に書く欄の一覧（`fill_keys`）。作成途中の md は残す | `{日付}_brief.md`・`{日付}_growth.md` |
| `growth.py build --company X [--date …]` | md を検証（構造・FILL・2章の年度がスクリプトの抽出と一致・分類が 一時/構造/不明・未回復の年に一時を使っていない・必須欄・禁止表現・LLM が書いた単位付きの数値が brief か骨組みにあるか）し、数値を raw から計算し直して成長性（良好 / 普通 / 懸念 / 判定保留）を書き込む | `{日付}_growth.json` |

モジュール: `gr_paths.py`（結果の場所と鮮度）、`gr_inputs.py`（入力一覧。抽出は `ff_inputs.py` を再利用）、`gr_series.py`（自社の年次系列: 売上高・営業利益・当期純利益・EPS・子会社株式の取得・自己株式の取得、EPS の分割調整、会社計画と実績、M&A の表。セルの読み取りは `pf_series.py`）、`gr_metrics.py`（CAGR、手順1〜5の判定と保守的判断、整合性チェック、収集の要求とヒント）、`gr_facts.py`（株式分割の記録、今期の進捗、販管費の内訳、保存済みの原本の検索）、`gr_brief.py`（材料。SWOT の弱み・脅威を引用）、`gr_doc.py`（骨組み・検証・結論）。テンプレートは `.ai/templates/growth/`。

スキル `safety`（`.ai/skills/safety.md`、STEP 2-3 安全性）からは `safety.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/safety/{分析日}_*`。数値と判定はすべてスクリプトが出し、LLM は数値の背景だけを書く。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `safety.py list` | `companies/` の企業と、安全性分析の状態（none / fresh / expired / triggered / draft）・結論・収益性の結論 | 1行の JSON |
| `safety.py check --company X` | 結果が有効か（180日以内で、使った節と年次の数値が変わっていないか）、材料があるか（自社の3指標と3年以上の推移・有利子負債 → collect-filings、競合の「安全性の指標」 → collect-peers-valuation）。STEP 1・収益性は前提にしない。`next` に次の作業 | 1行の JSON |
| `safety.py prepare --company X [--redo] [--skip-collect]` | 自社の年次系列（data/*.csv → 有報・財務時系列の表。CF の節も読む。有利子負債は行が無ければ借入金・社債の内訳の合計、どちらも無ければ不明）から自己資本比率・D/E・流動比率・ネットキャッシュを計算し、目安と同業平均による手順1、5年の推移（手順2）、有利子負債が増えた年の CF による借入目的の分類（手順3）を入れた骨組み（FILL は背景だけ）と材料（収益性の結果と outlook.md の金利・金融政策の行を抜粋。同じ節は1回、新しい「貸借・CF」の節より古い貸借・CF の節は載せない。リスク・財務3表は財務に関わる行だけ）を作る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_safety.md` |
| `safety.py build --company X [--date …]` | md を検証（構造・FILL・3章の年度がスクリプトの抽出と一致・必須欄・禁止表現・書いた数値が brief と md の記入済みの部分にあるか）し、数値を raw から計算し直して安全性（良好 / 普通 / 懸念 / 判定保留）を書き込む | `{日付}_safety.json` |

モジュール: `sf_paths.py`（結果の場所と鮮度）、`sf_inputs.py`（入力一覧。抽出は `ff_inputs.py` を再利用）、`sf_series.py`（自社・競合の貸借・CF の年次系列。表の読み取りは `pf_series.py` の Fields を使う。米国株の金額は raw の単位のまま）、`sf_metrics.py`（3指標、手順1〜4の判定、境界に近い比較、収集の要求）、`sf_brief.py`（材料）、`sf_doc.py`（骨組み・検証・結論）。テンプレートは `.ai/templates/safety/`。

スキル `valuation`（`.ai/skills/valuation.md`、STEP 3 バリュエーション）からは `valuation.py` を呼び出す。出力は `companies/{ticker}_{name}/analysis/valuation/{分析日}_*`。数値と判定はすべてスクリプトが出し、LLM は数値の背景と、PBR のバリュートラップに当たるときの改善策の有無（あり / なし / 不明）だけを書く。株価が日々動くため結果は7日有効。

| コマンド | 用途 | 主な出力 |
|---|---|---|
| `valuation.py list` | `companies/` の企業と、バリュエーション分析の状態（none / fresh / expired / triggered / draft）・結論・成長性の結論 | 1行の JSON |
| `valuation.py check --company X` | 結果が有効か（7日以内で、使った節と数値が変わっていないか、新しい成長性分析が無いか）、成長性分析が有効か（必須の上流 → `next: growth`）、材料があるか（株価データ 1・2・4章・競合 6章、株価の基準日が7日以内、競合 12章「EV/EBITDA の材料」 → collect-peers-valuation）。`next` に次の作業 | 1行の JSON |
| `valuation.py prepare --company X [--redo] [--skip-collect]` | 株価データ（株価・株式数・EPS・BPS・年次の PER・PBR の高値と安値・期末PER）、競合（6章の倍率、3章の売上高 CAGR、5章の ROE、11章の有利子負債と現金、12章の営業利益と減価償却費）、自社の年次（純利益・特別損益・自己資本は `pf_series`、営業利益・有利子負債・現金は `sf_series`、減価償却費は `cf_series`、分割調整した EPS は `gr_series`）と予想EPS（決算短信 → 株価データ 2章）から、PER・PBR・PEG・EV/EBITDA の各手順と共通ルール（過去レンジの位置 × 同業中央値との差）、STEP 3 の点数と最終確認、判定が変わる株価を入れた骨組み（FILL は背景だけ。当てはまらない欄は「該当なし」）と材料を作る。作成途中の md は残す | `{日付}_brief.md`・`{日付}_valuation.md` |
| `valuation.py build --company X [--date …]` | md を検証（構造・FILL・必須欄・改善策の回答の形・禁止表現・書いた数値が brief と md の記入済みの部分にあるか・概数）し、改善策の回答を使って数値を raw から計算し直し、4指標と STEP 3（割安 / 妥当 / 割高 / 判定保留）と判定シートの行を書き込む | `{日付}_valuation.json` |

モジュール: `va_paths.py`（結果の場所と鮮度）、`va_inputs.py`（入力一覧。抽出は `ff_inputs.py` を再利用）、`va_series.py`（株価データ・競合の倍率と EV の部品・自社の年次。年次は STEP 2 の series を再利用）、`va_rules.py`（全指標共通の判定ルール・組み合わせ・点数）、`va_metrics.py`（3-1〜3-4 の手順、STEP 3、判定が変わる株価、収集の要求、警告）、`va_brief.py`（材料）、`va_doc.py`（骨組み・検証・結論）。テンプレートは `.ai/templates/valuation/`。

### 書き込みガード（`tools/guard/write_guard.py`）

`.claude/settings.json` の PreToolUse hook として、Write / Edit の前に毎回実行される（標準ライブラリだけで動く。PATH 上の `python` を使う）。

- スクリプト専用のファイル（`data/`・`sources/`・`index.csv`・`tasks.json`・`status.md`・生成された表）の手書きをブロック
- `market/**/raw/*.md` は FILL 欄が残っている間だけ Edit を許可。`companies/*/raw/` の過去日付のファイルは変更禁止
- collect-market-info の実行中（`market/sessions/*/.running`）は、tasks.json の `allowed_files` 以外への書き込みをブロック
- `market/report/` の facts.json・brief.md・HTML は手書き禁止。outlook.md は Edit のみ（新規作成・上書き不可）で、過去の週の完成済みのものは変更禁止
- `companies/*/analysis/five-forces/`・`three-c/`・`moat/`・`swot/`・`profitability/`・`growth/`・`cash-flow/`・`safety/`・`valuation/` の brief.md・json は手書き禁止。five-forces.md・three-c.md・moat.md・swot.md・profitability.md・growth.md・cash-flow.md・safety.md・valuation.md は Edit のみで、過去の日付の build 済み（json がある）ものは変更禁止
- `companies/*/reports/` の company-report の HTML・json・facts.json・brief.md は手書き禁止。company-report.md は Edit のみで、過去の日付の build 済み（json がある）ものは変更禁止

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
