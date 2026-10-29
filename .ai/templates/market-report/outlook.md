# 地合い判断 — 日本・米国（${week} 週）

**分析日**: ${today}
**参照資料**: ${brief}（材料: 収集セッション ${session}、`market/data/`、`market/policy/`）
**地合い**: このファイルが地合い判断（企業分析はこのファイルを参照する）
**レポート**: ${html}

> market-report の prepare が骨組みを作る。LLM は `<!-- FILL:... -->` の部分だけを置き換える。見出し・表の列・上のヘッダー・スクリプトが記入済みの欄は変更しない。
> 地合いは3つの軸（金融環境 引き締め/中立/緩和、景気 減速/横ばい/拡大、市場のストレス 高い/普通/低い）と、そこから決まる注意の度合い（平常 / 注意 / 警戒）で表す。先行きの株価の予測ではない。軸の候補はスクリプトが出す（8章・brief.md 12.）。採用を変えるのは根拠があるときだけで、8章に理由を書く。1章の3軸は 8章の採用と同じにし、注意の度合いは採用から決まる語にする。4章の短期の判断は 1章の注意の度合いと同じ語にする（build が確かめる）。2段階で迷ったら注意の側を採るのは、採用を変えるかどうかの1回だけ。
> 根拠は brief.md にある数値・日付・文書名で示す。brief.md に無い情報（因果の一般論、業績・需給の推測）を補わない。値動きの理由は brief.md 14.1 の報道の記述（確度 一次・二次）があるときだけ、その出典を付けて書く。6章の注目点には 14.2 の市場予想・織り込みがあれば添える。数値は brief.md の転記だけ（比率・実質金利・乖離率は brief.md 11. の計算済みの値を使い、自分で計算しない）。時点に（古い）が付いた指標は足元の根拠にしない。株価・為替の水準予想、売買の推奨は書かない。「おそらく」「〜と思われる」は使わない。
> 情報源の欄は原典の名前で書く（例: 「FRED（S&P500）」「JPX 投資部門別売買」「日銀公表文 2026-09-18」「FOMC議事要旨 2026-10-07」）。「brief.md 1.」のような社内ファイルの節番号は書かない（HTML の読者は brief.md を見られない）。
> 文字数の目安（スライドに載る量。超えると build が warnings で知らせる）: 判断の要約 80 字、キーメッセージ 100 字、見たもの 120 字、結論 60 字、4章の各欄 60 字。

## 1. 総合判断

| 市場 | 注意の度合い | 金融環境 | 景気 | 市場のストレス | 前回（${prev_week}） | 判断の要約 |
|---|---|---|---|---|---|---|
| 日本 | <!-- FILL:judgment-japan --> | <!-- FILL:money-japan --> | <!-- FILL:economy-japan --> | <!-- FILL:stress-japan --> | ${prev_japan} | <!-- FILL:summary-japan 80字以内。注意の度合いを決めた軸と数値。前回から変えたらその理由 --> |
| 米国 | <!-- FILL:judgment-us --> | <!-- FILL:money-us --> | <!-- FILL:economy-us --> | <!-- FILL:stress-us --> | ${prev_us} | <!-- FILL:summary-us 80字以内。注意の度合いを決めた軸と数値。前回から変えたらその理由 --> |

## 2. 今週のキーメッセージ

<!-- FILL:key-messages 3〜5項目の箇条書き（- で始める）。各項目「**見出し（20字以内）**: 事実（数値・日付）→ 市場にとっての意味（出典）」で100字以内 -->

## 3. 市場動向

各表は「見たもの → 情報源 → 結論」。見たものは決め手の数値2〜4個に絞る（120字以内。スライドの表・チャートに全数値が載るので並べ直さない）。結論は1文・60字以内。

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

短期 = 今後4週、中期 = 6か月程度、長期 = 1〜3年。
基本シナリオは「何が続く／変わる前提か」を書き、水準の予想はしない。短期の間に FOMC・日銀会合があるときは、上振れ・下振れ要因を会合の結果（据え置き／利上げ など）で分けて書く。確認する指標・イベントは brief.md の日程・指標から選ぶ。各欄 60 字以内。判断は注意の度合い（平常 / 注意 / 警戒）で、短期は 1章と同じ語。中期・長期は、その期間に注意が要る材料の多さで決める。中期・長期の判断を前回から変えたら 9章に理由を書く。

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

## 8. 軸ごとの評価

候補はスクリプトが brief.md 12. の信号から出した評価。採用は候補を写してある。変えるのは、信号が拾えない材料（金融環境なら中央銀行の公表文・議事要旨、景気なら月例経済報告・ベージュブック、時点の古い信号など）が根拠になるときだけで、そのときは採用を書き換え、理由に指標と時点か文書名を書く。変えない行の理由は「—」。

| 市場 | 軸 | 候補 | 採用 | 変えた理由 |
|---|---|---|---|---|
${viewpoint_rows}

## 9. 前回からの変更

4章の判断を前回（${prev_week}）と比べる。前回はスクリプトが記入済み。

| 期間 | 市場 | 前回 | 変えた理由 |
|---|---|---|---|
${change_rows}

## 10. 企業分析への引き継ぎ

スクリプトが記入する（手で変えない。build が facts.json と照合する）。企業分析は金利・為替・株価の局面をこの表から引用する。

| 市場 | 項目 | 値 | 時点 | 出典 |
|---|---|---|---|---|
${handoff_rows}

## 11. やさしい要約（はじめての方へ）

投資を始めたばかりの人が読む。専門用語（スプレッド・実質金利・益利回り・①〜④ の記号など）を使わず、ふだんの言葉で書く。数値は各項目1つまで。売買や「様子を見る」などの行動を勧める書き方はしない（起きていることと予定だけを書く）。各項目 60 字以内。

### 今週を3行で

<!-- FILL:plain-summary 箇条書き3つ（- で始める）。1つ目は日本、2つ目は米国の状況、3つ目は今週いちばん大事な出来事 -->

### 気をつけること

<!-- FILL:plain-caution 箇条書き1つ（- で始める）。今後1か月で値動きが大きくなりうる出来事と、その日付 -->

## 12. 業種の動き

スクリプトが記入する（手で変えない。build が facts.json と照合する）。1か月の騰落率と指数との差で並べた上位・下位3業種。業種 ETF の終値から計算した値で、動いた理由は含まない。

| 市場 | 区分 | 業種 | 1か月 | 指数との差（1か月） | 3か月 | 時点 |
|---|---|---|---|---|---|---|
${sector_rows}
