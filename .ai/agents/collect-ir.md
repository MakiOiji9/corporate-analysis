# 担当: collect-ir（企業サイト・IR・プレスリリース）

collect-company-info の **Phase 1** を担当する。親（オーケストレーター）から起動され、他の担当と**同時に**動く。

## 前提として読むファイル
- `.ai/instructions/policy.md`（禁止事項）
- `.ai/skills/collect-company-info.md` の「保存ルール」「ツール」「同時実行のルール」
- `.ai/templates/collect-company-info/source-access.md`

## 入力（親のプロンプトで渡される）
ticker, name, url, market, mode, 企業ディレクトリ, 収集日, 取得経路（EDINET キー有無・ブラウザ可否）, update の場合は前回収集日

## 書いてよいファイル（これ以外は書かない）
- `raw/ir/{収集日}_business-overview.md`, `raw/ir/{収集日}_mid-term-plan.md`, `raw/ir/{収集日}_ir-materials-index.md`
- `raw/news/{収集日}_press-releases.md`
- `fetch.py` 経由の `sources/`
- **書かない**: `status.md`, `overview.md`, `summaries/`, `data/`, 他担当の raw
- mode=update の差分ファイルは、今回の範囲の章だけを書く。範囲外の章は見出しごと書かない（「変更なし」と書かない。前回の値を再掲しない。collect-company-info.md の保存ルール）

## 手順
1. 指定URLを起点に、会社概要・事業紹介・IR・ニュースのページを WebFetch で読む
2. IR資料一覧・ニュース一覧が JS で描画されるウィジェット（HTML に `eir-parts.net`、`data-area-name` 等）なら**解析しない**。`source-access.md` の「IR一覧の代替経路」で一覧を作る
3. 決算説明会資料・質疑応答・中期経営計画は `fetch.py --type presentation|qa|plan --text` で原本を保存し、`find_pages.py` で必要ページだけ読む。KPI（顧客数、上位顧客比率、リピート率、人員数、採用、単価・稼働率など会社が開示している指標）を拾う
4. 中期経営計画が無い場合は、有報の該当文言（`find_pages.py find <有報txt> 中期経営計画`）を引用して「策定・公表なし」と書き、代わりの開示（方針・単年度予想）を記録する。有報の原本は collect-filings が保存するが、同じ URL を `fetch.py` で取得すれば重複は自動でスキップされる
5. **継続率・解約率・ストック型売上の比率**（雛形 business-overview.md 7章）と**値上げ・価格改定の実績**（同 8章）はモート分析（スイッチングコスト・ブランド）に使う。決算説明会資料・統合報告書・有報を `find_pages.py find <txt> "継続率" "解約率" "リピート" "ストック" "価格改定" "値上げ" "単価"` で探し、該当ページだけ読む。過去5年の価格改定は、その後の販売数量・顧客数・受注の変化と一緒に書く。開示が無い指標は「—（開示なし）」とし、探した資料名を出典列に書く。取れなかった指標は、親への報告の未取得項目に「解約率・ストック型売上の比率」「値上げ・価格改定の実績」の形で書く（status.md の未取得項目になり、モート分析は再収集を求めなくなる）
6. プレスリリースは直近1年（update は前回収集日の翌日以降）。期末後のコーポレートアクション（株式分割・株式交換・自己株式・商号変更）を必ず抜き出して報告の5章に書く

| 収集対象 | 保存先（雛形 `.ai/templates/collect-company-info/raw/`） |
|---|---|
| 事業内容、主力製品・サービス、セグメント構成、顧客層、主要KPI、継続率・解約率・ストック型売上の比率、値上げ・価格改定の実績 | `raw/ir/{収集日}_business-overview.md`（business-overview.md） |
| 中期経営計画（目標値・重点施策・資本政策・株主還元方針） | `raw/ir/{収集日}_mid-term-plan.md`（mid-term-plan.md） |
| IR資料一覧（資料名・対象期間・URL・原本の保存パス） | `raw/ir/{収集日}_ir-materials-index.md`（ir-materials-index.md） |
| プレスリリース・重要ニュース（日付・見出し・要旨・URL） | `raw/news/{収集日}_press-releases.md`（press-releases.md） |

## 報告
`.ai/templates/collect-company-info/agent-report.md` の形式で返答する。次回決算発表予定日（IRカレンダー等）が分かれば5章に書く。
