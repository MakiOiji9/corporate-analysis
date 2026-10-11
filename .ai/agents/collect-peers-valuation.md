# 担当: collect-peers-valuation（競合・株価指標）

collect-company-info の **Phase 5・6** を担当する。親（オーケストレーター）から起動され、他の担当と**同時に**動く。

## 前提として読むファイル
- `.ai/instructions/policy.md`（禁止事項）
- `.ai/skills/collect-company-info.md` の「保存ルール」「ツール」「同時実行のルール」
- `.ai/templates/collect-company-info/source-access.md`

## 入力（親のプロンプトで渡される）
ticker, name, url, market, mode, 企業ディレクトリ, 収集日, update の場合は「株価のみ」か「競合も」の範囲指定と、前回の競合リスト

## 書いてよいファイル（これ以外は書かない）
- `raw/market/{収集日}_competitors.md`, `raw/ir/{収集日}_valuation-data.md`
- `fetch.py` 経由の `sources/`（競合の短信など）
- **書かない**: `status.md`, `overview.md`, `summaries/`, `data/`（`tdnet_summary.py` を競合に使う場合は `--company` を付けず標準出力だけ使う）, 他担当の raw

## Phase 5: 競合
1. 主力事業を自分で特定する（collect-market と同じ手早い確認でよい）
2. 主力事業が近く、規模が極端に違わない同業他社を2〜3社選ぶ。選定理由（事業の類似点・規模）を記載する。update で前回の競合リストがあれば原則それを使う
3. 数値は可能なら各社の決算短信 iXBRL（`fetch.py --company {自社dir} --type peer-tanshin` → `tdnet_summary.py <htm>`、`--company` なし）で一次確認する。IRBANK 等の二次情報だけの値は確度「二次」

| 項目 |
|---|
| 売上高・営業利益・営業利益率（直近と5年推移） |
| 市場シェア |
| 売上高の3年CAGR計算に必要な売上高（3年前と直近） |
| ROE、自己資本比率 |
| PER・PBR・EV/EBITDA（直近値） |
| 主力製品と強み（競合のIR資料で本人が主張しているもの） |

保存先: `raw/market/{収集日}_competitors.md`（雛形 competitors.md）

## Phase 6: 自社の株価・バリュエーション

| 項目 |
|---|
| 現在株価（取得日時を明記）、時価総額、発行済株式数（自己株式を除く） |
| EPS（実績・会社予想）、BPS |
| PER・PBR・EV/EBITDA の過去5〜10年の推移（年次の最高・最低・平均） |
| アナリスト予想のEPS成長率（入手できる場合のみ） |

- EPS・BPS・株式数は、`data/tdnet_facts.csv` があれば読んでよい（読むだけ。collect-filings が同時に更新中でも、ファイルは原子的に置き換わるので壊れた状態は見えない）。無ければ最新の短信を自分で確認する
- **期末後のコーポレートアクション**（株式分割・株式交換・自己株式・新株予約権行使）をプレスリリース一覧（IRBANK 適時開示一覧など）で確認し、株式数・1株指標への影響を注記する

保存先: `raw/ir/{収集日}_valuation-data.md`（雛形 valuation-data.md）

## 報告
`.ai/templates/collect-company-info/agent-report.md` の形式で返答する。5章に主力事業の判定、株価の基準日、確認したコーポレートアクションを書く。
