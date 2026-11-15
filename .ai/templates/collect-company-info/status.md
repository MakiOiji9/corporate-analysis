# データ鮮度・未取得項目 — {企業名}

**最終更新**: YYYY-MM-DD（mode={full / update}）

> collect-company-info を実行するたびに上書きする。`mode=update` はまずこのファイルと `sources/manifest.csv` を読む。

## 1. データ鮮度

| 区分 | 最新データの時点 | 取得日 | raw ファイル | 次回更新トリガー |
|---|---|---|---|---|
| 株価・株価指標 | YYYY-MM-DD 終値 | YYYY-MM-DD | raw/ir/YYYY-MM-DD_valuation-data.md | 再実行のたび |
| 四半期決算 | YYYY年M月期 Qn | YYYY-MM-DD | data/tdnet_facts.csv | 次回決算発表予定日: YYYY-MM-DD |
| 通期決算・会社予想 | YYYY年M月期 | YYYY-MM-DD | raw/ir/YYYY-MM-DD_financials-historical.md | 本決算発表（例年 M月） |
| 有価証券報告書 | 第n期（YYYY年M月期） | YYYY-MM-DD | raw/filings/YYYY-MM-DD_{期}_yuho.md | 有報提出（例年 M月） |
| プレスリリース | 〜YYYY-MM-DD | YYYY-MM-DD | raw/news/YYYY-MM-DD_press-releases.md | 再実行のたび（前回以降の差分） |
| 業界・市場 | 調査公表 YYYY年M月 | YYYY-MM-DD | raw/market/YYYY-MM-DD_industry-overview.md | 年1回 |
| 競合 | 各社の直近期 | YYYY-MM-DD | raw/market/YYYY-MM-DD_competitors.md | 年1回、または競合の本決算後 |

## 2. 未取得項目（次回優先して取りにいく）

<!-- 時点は、取りにいって取れなかったときの自社の最新の決算期（raw の有報・10-K の期。例 2026-02期）。分析スクリプトはこの記録を、自社の新しい決算期の有報・10-K が raw に入るまで「取れないもの」として扱い、再収集を求めない。新しい期の有報が入ると記録は失効し、必要な材料はもう一度だけ求められる（取れないものを毎回取りにいかず、年に1回は取り直す）。再挑戦しても取れなければ、時点を新しい期に書き換える -->
| 項目 | 理由 | 次回試す取得方法 | 時点（自社の決算期） |
|---|---|---|---|
| — | — | — | — |

## 3. 期末後のコーポレートアクション（株式数・指標に影響するもの）

| 日付 | 内容 | 影響 |
|---|---|---|
| — | — | — |
