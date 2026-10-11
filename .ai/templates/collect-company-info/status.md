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

| 項目 | 理由 | 次回試す取得方法 |
|---|---|---|
| — | — | — |

## 3. 期末後のコーポレートアクション（株式数・指標に影響するもの）

| 日付 | 内容 | 影響 |
|---|---|---|
| — | — | — |
