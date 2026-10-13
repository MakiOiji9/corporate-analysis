# 担当: collect-filings（有価証券報告書・財務時系列・会社計画）

collect-company-info の **Phase 2・3** を担当する。親（オーケストレーター）から起動され、他の担当と**同時に**動く。
数値はスクリプトで抽出し、PDF の全文は読まない。

## 前提として読むファイル
- `.ai/instructions/policy.md`（禁止事項）
- `.ai/skills/collect-company-info.md` の「保存ルール」「ツール」「同時実行のルール」
- `.ai/templates/collect-company-info/source-access.md`

## 入力（親のプロンプトで渡される）
ticker, name, url, market, mode, 企業ディレクトリ, 収集日, 取得経路（EDINET キー有無）, update の場合は前回収集日

## 書いてよいファイル（これ以外は書かない）
- `raw/filings/{収集日}_{決算期}_{書類種別}.md`, `raw/ir/{収集日}_financials-historical.md`
- `data/financials.csv`, `data/tdnet_facts.csv`（スクリプト経由のみ）
- `fetch.py` / `edinet.py fetch` 経由の `sources/`
- **書かない**: `status.md`, `overview.md`, `summaries/`, 他担当の raw

## Phase 2: 公式開示書類（最新の有報 / 10-K）
- EDINET 経路: `edinet.py list --code {ticker} --fy-end-month {決算月} --years 1` → `edinet.py fetch --doc-id {docID} --company {dir} --kind csv`（数値用）と `--kind pdf`（定性情報用）
- PDF 経路: IR資料一覧・EDINET DB で有報 PDF の URL（例 `ssl4.eir-parts.net/doc/{code}/yuho_pdf/{書類番号}/00.pdf`）を見つけ、`fetch.py --type yuho --text`
- 米国株: 10-K（SEC EDGAR）を `fetch.py --type 10k --text`
- `find_pages.py cover` で**表紙の【事業年度】を確認して期を判定**、`toc` でページを特定し、必要ページだけ読む

抽出項目（雛形 `raw/yuho.md`）: セグメント情報（単一セグメントなら収益の分解）、主要な販売先（売上10%以上）、事業等のリスク要旨、主要な原材料・調達先、研究開発・特許・許認可、従業員数・設備投資、財務3表の主要項目（`find_pages.py fin` または `xbrl_financials.py`）、特別利益・特別損失の内訳、発行済株式数・自己株式数

保存先: `raw/filings/{収集日}_{決算期}_{書類種別}.md`（例 `2026-10-11_2026-03_yuho.md`）

## Phase 3: 財務データの時系列（5〜10年）
1. **年次財務**
   - EDINET 経路: 過去の有報（最新期と5期前などで10年をカバー）を `edinet.py fetch --kind csv` → `xbrl_financials.py {展開先} --company {dir}` を**古い順に**実行
   - PDF 経路: 過去の有報 PDF を `fetch.py --text` → `find_pages.py fin`（各有報に2期分）
   - どちらでも取れない年度だけ IRBANK・株探で補い、確度「二次」と明記
2. **会社計画と実績**: 各期の本決算短信の「次期予想」が期初予想。iXBRL（.htm）を `fetch.py` → `tdnet_summary.py --company {dir}`。期中修正は「業績予想の修正」開示から。古い年度は短信 PDF・株探記事で補い確度を明記
3. **直近四半期**: 最新の四半期（中間）短信も `tdnet_summary.py` で取り込む
4. `render_tables.py financials / forecasts / quarterly` の出力を raw に貼る

| 区分 | 項目 |
|---|---|
| 損益 | 売上高、売上原価、販管費、営業利益、経常利益、当期純利益、EPS |
| 貸借 | 総資産、自己資本、有利子負債、現金同等物、流動資産、流動負債、売上債権、棚卸資産、BPS |
| CF | 営業CF、投資CF、財務CF、減価償却費、設備投資額、子会社株式取得による支出 |
| 株主還元 | 配当総額、1株配当、自社株買い額 |
| 比率 | ROE、営業利益率、自己資本比率（取得できなければ計算せず `—`） |
| 会社計画 | 期初予想・期中修正・実績 |
| 四半期 | 直近の四半期累計の実績、通期予想の修正有無 |

保存先: `raw/ir/{収集日}_financials-historical.md`（雛形 financials-historical.md）

- 収益性分析（profitability）は 売上高・当期純利益（親会社株主に帰属）・総資産・自己資本（無ければ自己資本比率）が揃った年を5年以上要する。どの経路でも5年揃わなかったときは、親への報告の未取得項目に「収益性の財務時系列（N年分のみ）」と書く（status.md の未取得項目になり、収益性分析は再収集を求めなくなる）

## 報告
`.ai/templates/collect-company-info/agent-report.md` の形式で返答する。5章に**主力事業の判定**（セグメント情報で営業利益構成比が最大のもの、単一ならその旨）とデータの時点（最新の有報・四半期）を必ず書く。
