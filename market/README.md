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
2. `LATEST.md`（最新の完了セッションと文書種別ごとの最新版への入口）と、そこから辿れる `status.md` の「7. 要確認事項」を確認する
3. スキル `market-report` を実行する（例: `/market-report`）。今週の収集が無ければ先に 1. を自動で実行し、
   `report/{週の月曜}_market-report.html`（プレゼン形式の単一 HTML）と `report/{週の月曜}_outlook.md`（地合い判断と短期・中期・長期の展望）を作る
4. 次回の企業分析前に `report/` の最新の `outlook.md` を参照する

情報の鮮度: 時系列（`data/`）は毎回上書き更新、文書（`policy/`）は新しい版だけ追加、日程（`sessions/…/raw/calendar-*`）はセッションごとに作り直す。
どれが最新かは `LATEST.md` を見る。要旨を作り直すときは `market_collect.py reopen`（`tools/README.md`）。

## ディレクトリ構造

```
LATEST.md                          # 最新の状態への入口（finalize が生成）
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
report/                            # 週次の地合いレポート（market-report。{週} は出力週の月曜日）
├── {週}_facts.json / {週}_brief.md # レポートの数値と執筆の材料（スクリプトが生成）
├── {週}_outlook.md                # 地合い判断（強気/中立/慎重/弱気）と短期・中期・長期の展望
└── {週}_market-report.html        # プレゼンテーション形式の単一 HTML
```

収集対象の情報源と追加方法は `.ai/templates/collect-market-info/source-access.md` を参照。

## 地合い判断の4段階

| 判断 | 意味 |
|---|---|
| 強気 | 複数のマクロ要因が追い風。積極的な新規投資を検討 |
| 中立 | 特段の追い風・逆風なし。個別銘柄の実力で判断 |
| 慎重 | 一部にリスク要因あり。ポジションを抑えめに |
| 弱気 | 複数のリスク要因が重なる。新規投資を控える |
