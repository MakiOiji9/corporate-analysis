# 地合い判断 — 日本・米国（${week} 週）

**分析日**: ${today}
**参照資料**: ${brief}（材料: 収集セッション ${session}、`market/data/`、`market/policy/`）
**地合い**: このファイルが地合い判断（企業分析はこのファイルを参照する）
**レポート**: ${html}

> market-report の prepare が骨組みを作る。LLM は `<!-- FILL:... -->` の部分だけを置き換える。見出し・表の列・上のヘッダー・スクリプトが記入済みの欄は変更しない。
> 判断は 強気 / 中立 / 慎重 / 弱気 のどれか1語。2段階で迷ったら低い方（不利な方）を採る。
> 根拠は brief.md にある数値・日付・ファイル名で示す。brief.md に無い情報を補わない。株価・為替の水準予想、売買の推奨は書かない。「おそらく」「〜と思われる」は使わない。

## 1. 総合判断

| 市場 | 地合い判断 | 前回（${prev_week}） | 判断の要約 |
|---|---|---|---|
| 日本 | <!-- FILL:judgment-japan --> | ${prev_japan} | <!-- FILL:summary-japan 1〜2文。決め手になった要因と数値 --> |
| 米国 | <!-- FILL:judgment-us --> | ${prev_us} | <!-- FILL:summary-us 1〜2文。決め手になった要因と数値 --> |

## 2. 今週のキーメッセージ

<!-- FILL:key-messages 3〜5項目の箇条書き（- で始める）。各項目「事実（数値・日付）→ 市場にとっての意味」（出典: ファイル名） -->

## 3. 市場動向

各表は「見たもの → 情報源 → 結論」。結論は1〜2文。

### 3.1 株価・需給・バリュエーション

| 市場 | 見たもの | 情報源 | 結論 |
|---|---|---|---|
| 日本 | <!-- FILL:equity-japan-seen --> | <!-- FILL:equity-japan-source --> | <!-- FILL:equity-japan-conclusion --> |
| 米国 | <!-- FILL:equity-us-seen --> | <!-- FILL:equity-us-source --> | <!-- FILL:equity-us-conclusion --> |

### 3.2 金利・為替

| 市場 | 見たもの | 情報源 | 結論 |
|---|---|---|---|
| 日本 | <!-- FILL:rates-japan-seen --> | <!-- FILL:rates-japan-source --> | <!-- FILL:rates-japan-conclusion --> |
| 米国 | <!-- FILL:rates-us-seen --> | <!-- FILL:rates-us-source --> | <!-- FILL:rates-us-conclusion --> |

### 3.3 金融政策

| 市場 | 見たもの | 情報源 | 結論 |
|---|---|---|---|
| 日本 | <!-- FILL:policy-japan-seen --> | <!-- FILL:policy-japan-source --> | <!-- FILL:policy-japan-conclusion --> |
| 米国 | <!-- FILL:policy-us-seen --> | <!-- FILL:policy-us-source --> | <!-- FILL:policy-us-conclusion --> |

### 3.4 マクロ（物価・雇用・景気）

| 市場 | 見たもの | 情報源 | 結論 |
|---|---|---|---|
| 日本 | <!-- FILL:macro-japan-seen --> | <!-- FILL:macro-japan-source --> | <!-- FILL:macro-japan-conclusion --> |
| 米国 | <!-- FILL:macro-us-seen --> | <!-- FILL:macro-us-source --> | <!-- FILL:macro-us-conclusion --> |

### 3.5 財政・政策・政治

| 市場 | 見たもの | 情報源 | 結論 |
|---|---|---|---|
| 日本 | <!-- FILL:fiscal-japan-seen --> | <!-- FILL:fiscal-japan-source --> | <!-- FILL:fiscal-japan-conclusion --> |
| 米国 | <!-- FILL:fiscal-us-seen --> | <!-- FILL:fiscal-us-source --> | <!-- FILL:fiscal-us-conclusion --> |

## 4. 展望

短期 = 今後1か月（次回の FOMC・日銀会合まで）、中期 = 6か月程度、長期 = 1〜3年。
基本シナリオは「何が続く／変わる前提か」を書き、水準の予想はしない。確認する指標・イベントは brief.md の日程・指標から選ぶ。

| 期間 | 市場 | 判断 | 基本シナリオ | 上振れ要因 | 下振れ要因 | 確認する指標・イベント |
|---|---|---|---|---|---|---|
| 短期 | 日本 | <!-- FILL:short-japan-judgment --> | <!-- FILL:short-japan-scenario --> | <!-- FILL:short-japan-upside --> | <!-- FILL:short-japan-downside --> | <!-- FILL:short-japan-watch --> |
| 短期 | 米国 | <!-- FILL:short-us-judgment --> | <!-- FILL:short-us-scenario --> | <!-- FILL:short-us-upside --> | <!-- FILL:short-us-downside --> | <!-- FILL:short-us-watch --> |
| 中期 | 日本 | <!-- FILL:mid-japan-judgment --> | <!-- FILL:mid-japan-scenario --> | <!-- FILL:mid-japan-upside --> | <!-- FILL:mid-japan-downside --> | <!-- FILL:mid-japan-watch --> |
| 中期 | 米国 | <!-- FILL:mid-us-judgment --> | <!-- FILL:mid-us-scenario --> | <!-- FILL:mid-us-upside --> | <!-- FILL:mid-us-downside --> | <!-- FILL:mid-us-watch --> |
| 長期 | 日本 | <!-- FILL:long-japan-judgment --> | <!-- FILL:long-japan-scenario --> | <!-- FILL:long-japan-upside --> | <!-- FILL:long-japan-downside --> | <!-- FILL:long-japan-watch --> |
| 長期 | 米国 | <!-- FILL:long-us-judgment --> | <!-- FILL:long-us-scenario --> | <!-- FILL:long-us-upside --> | <!-- FILL:long-us-downside --> | <!-- FILL:long-us-watch --> |

## 5. リスク要因

影響は 大 / 中 / 小。市場は 日本 / 米国 / 日米。

| リスク | 市場 | 影響 | 兆候を確認する指標 | 根拠（情報源） |
|---|---|---|---|---|
<!-- FILL:risks 3〜6行の表の行（| リスク | 市場 | 影響 | 指標 | 根拠 |）に置き換える -->

## 6. 注目イベント（今後4週）

日付・市場・イベントはスクリプトが記入済み。注目点（何が分かるか・どの判断に効くか）だけを書く。

| 日付 | 市場 | イベント | 注目点 |
|---|---|---|---|
${event_rows}

## 7. データの限界

スクリプトが検出した欠損:

${limits}

<!-- FILL:limits 上の欠損や status.md の要確認事項のうち、判断に影響するものを箇条書き（- で始める）。無ければ「- 判断に影響する欠損なし」 -->
