# 担当: collect-market（業界・市場）

collect-company-info の **Phase 4** を担当する。親（オーケストレーター）から起動され、他の担当と**同時に**動く。

## 前提として読むファイル
- `.ai/instructions/policy.md`（禁止事項）
- `.ai/skills/collect-company-info.md` の「保存ルール」「ツール」「同時実行のルール」
- `.ai/templates/collect-company-info/source-access.md`

## 入力（親のプロンプトで渡される）
ticker, name, url, market, mode, 企業ディレクトリ, 収集日, update の場合は前回の industry-overview の日付

## 書いてよいファイル（これ以外は書かない）
- `raw/market/{収集日}_industry-overview.md`
- `fetch.py` 経由の `sources/`（業界統計の PDF などを保存する場合）
- **書かない**: `status.md`, `overview.md`, `summaries/`, 他担当の raw

## 手順
1. **主力事業を自分で特定する**（collect-filings を待たない）。セグメント情報で営業利益構成比が最大のもの、単一セグメントなら全社。
   - 手早い確認: 最新の有報 PDF を `fetch.py --type yuho --text`（他担当が取得済みなら DUPLICATE として既存パスが返る）→ `find_pages.py find <txt> "セグメント"` で該当ページだけ読む。企業サイトの事業紹介で足りる場合はそれでよい
2. 業界団体の統計、調査会社のレポート、官公庁の統計、競合のIR資料を優先して web 検索する。**各値に確度（一次 / 二次 / 検索要約）を付ける**

| 収集対象 |
|---|
| 市場規模と成長率（過去実績・将来予測。予測は出典と予測主体を明記） |
| 上位企業とシェア分布、シェアの推移 |
| 参入に必要な条件（初期投資規模、許認可、技術・ブランド）、過去5年の主な新規参入 |
| 代替製品・代替手段とその普及状況 |
| 顧客の購買決定要因（価格・品質・性能・サポート・ブランドなど） |
| 原材料・部品の調達構造、過去の原材料価格高騰の事例 |
| 業界全体の利益率の推移 |
| 技術革新・規制変更・特許切れなど、業界構造を変えうる要因 |

保存先: `raw/market/{収集日}_industry-overview.md`（雛形 industry-overview.md）

## 報告
`.ai/templates/collect-company-info/agent-report.md` の形式で返答する。5章に自分が採用した**主力事業の判定と根拠**を書く（親が collect-filings の判定と照合する）。
