# market/ — 地合い分析

マクロ経済・国の方針・政治情報を統合し、株式市場の地合いを判断するディレクトリです。

## 目的

トップダウン分析の起点として、以下を評価します。

- 金融政策（日銀・FRB の方向性）
- 財政政策（政府の経済対策・予算方針）
- 政治動向（選挙・政権交代・規制変化）
- マクロ指標（CPI・GDP・金利・為替）

## ワークフロー

1. スキル `collect-market-info` を実行する（例: `/collect-market-info both topic=weekly`）
   - スクリプトが時系列（日銀・e-Stat・財務省・JPX・FRED・CFTC）を取得し、新しく出た政策文書を `policy/` に取り込む
   - LLM は文書の要旨化と、政治・イベント日程の検索だけをサブエージェントで並列に行う
2. `sessions/YYYY-MM-DD_{topic}/status.md` で取得結果を確認する
3. `raw/` と `policy/` の要旨をもとに `analysis.md` と `outlook.md` を作る（地合い判断）
4. 次回の企業分析前に最新の `outlook.md` を参照する

## ディレクトリ構造

```
policy/{japan,us}/                 # 国家方針・財政・金融政策の文書ライブラリ（新しい版だけ追加）
├── index.csv                      # 資料台帳
├── sources/                       # 原本（git 管理外。manifest.csv だけコミット）
└── raw/YYYY-MM-DD_{doc_key}.md    # 文書ごとの要旨
data/{japan,us}_series.csv         # マクロ指標・需給の時系列
sessions/YYYY-MM-DD_{topic}/
├── tasks.json / status.md         # 収集の記録（スクリプトが生成）
├── raw/
│   ├── indicators-{market}.md     # マクロ指標・需給の表
│   ├── calendar-{market}.md       # 政治・イベント日程と市場指標
│   └── policy-digest.md           # 今回追加された文書と最新版の一覧
├── analysis.md                    # マクロ要因の統合分析
└── outlook.md                     # 地合い判断（強気/中立/慎重/弱気）
```

収集対象の情報源と追加方法は `.ai/templates/collect-market-info/source-access.md` を参照。

## 地合い判断の4段階

| 判断 | 意味 |
|---|---|
| 強気 | 複数のマクロ要因が追い風。積極的な新規投資を検討 |
| 中立 | 特段の追い風・逆風なし。個別銘柄の実力で判断 |
| 慎重 | 一部にリスク要因あり。ポジションを抑えめに |
| 弱気 | 複数のリスク要因が重なる。新規投資を控える |
