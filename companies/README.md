# companies/ — 企業個別分析

銘柄ごとの詳細分析を格納するディレクトリです。

## ディレクトリ命名規則

`{ticker}_{name}/`　例: `7203_toyota`, `9984_softbank`, `AAPL_apple`

## 企業ディレクトリの構造

スキル `collect-company-info` を実行すると、以下の構成が作成されます（詳細は `.ai/instructions/output-format.md`）。
2回目以降は `mode=update` で、前回以降の差分だけを追加します。

```
{ticker}_{name}/
├── overview.md          # 企業概要・投資テーゼ・現在の判断
├── status.md            # データ鮮度・未取得項目・次回更新トリガー
├── sources/             # ダウンロードした原本（git 管理外。manifest.csv だけコミット）
├── data/                # スクリプト生成の構造化データ（financials.csv, tdnet_facts.csv）
├── raw/                 # 生データ（収集後は変更禁止）
│   ├── ir/              # 事業概要・中期経営計画・IR資料一覧・財務時系列・株価指標
│   ├── filings/         # 有価証券報告書(EDINET) / 10-K(SEC EDGAR)
│   ├── news/            # ニュース・プレスリリース
│   └── market/          # 業界・市場データ・競合情報
├── summaries/           # raw/ の要約（business / financials / valuation）
├── sessions/            # 日付付き分析セッション
│   └── YYYY-MM-DD_{topic}/
│       └── judgment-sheet.md
└── reports/             # 完成した投資レポート
```

原本は git で管理しないため、別の環境では `sources/manifest.csv` の URL から再取得できます。

## 3STEP分析フロー

企業分析フレームワーク.md に従い、以下の順で実行します。

| STEP | 観点 | 問い | C判定なら |
|---|---|---|---|
| 1 | 事業・競争環境 | 良いビジネスか | その時点で終了 |
| 2 | 財務 | 数字が裏付けているか | その時点で終了 |
| 3 | バリュエーション | 今の株価は妥当か | — |

## 情報源

- **日本株**: EDINET（有価証券報告書）、決算短信、IR資料
- **米国株**: SEC EDGAR（10-K/10-Q）、決算リリース
- **共通**: 証券会社ツール、業界団体統計、競合のIR資料
