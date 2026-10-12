# 出力形式規則（Output Format）

## 言語

| 対象 | 言語 |
|---|---|
| ユーザーへの応答 | 日本語 |
| ファイル名・ディレクトリ名 | 英語（半角小文字、ハイフン区切り） |
| 分析コンテンツ（ファイルの中身） | 日本語 |

## ファイル命名規則

| 対象 | 形式 | 例 |
|---|---|---|
| 分析セッション | `YYYY-MM-DD_{topic}` | `2026-10-11_q2-earnings` |
| 投資レポート | `YYYY-MM-DD_{type}.md` | `2026-10-11_initiation.md` |
| 企業ディレクトリ | `{ticker}_{name}` | `7203_toyota`, `AAPL_apple` |

## 出力ディレクトリ構造

### 企業分析

```
companies/{ticker}_{name}/
├── overview.md                  # 企業概要・投資テーゼ・現在の判断・次回見直し日
├── status.md                    # データ鮮度・未取得項目・次回更新トリガー（収集のたびに上書き）
├── sources/                     # ダウンロードした原本（git 管理外）
│   ├── manifest.csv             # 原本の台帳（URL・書類ID・取得日・sha256）※これだけコミット
│   └── YYYY-MM-DD/              # 取得日ごとの原本（PDF/HTML/ZIP）とテキスト化したもの
├── data/                        # スクリプトが生成する構造化データ（手で編集しない）
│   ├── financials.csv           # 年次財務（xbrl_financials.py）
│   └── tdnet_facts.csv          # 決算短信のサマリー（tdnet_summary.py）
├── raw/                         # 収集した生データ（分析後は変更禁止）
│   ├── ir/                      # IR資料・決算資料・中期経営計画
│   ├── filings/                 # 有価証券報告書(EDINET) / 10-K(SEC EDGAR)
│   ├── news/                    # ニュース・プレスリリース
│   └── market/                  # 業界・市場データ・競合情報
├── summaries/                   # raw/ から作成した要約（評価・判定は含めない）
│   ├── business.md              # 事業・市場・競合の要約
│   ├── financials.md            # 財務主要項目の時系列・同業比較
│   └── valuation.md             # 株価指標の現在値・過去レンジ・同業比較
├── analysis/                    # 有効期間を持つ分析（種類ごと。スキル定義に従う）
│   ├── five-forces/             # ファイブフォース分析（five-forces。365日有効）
│   │   ├── YYYY-MM-DD_brief.md          # 執筆の材料（スクリプトが生成）
│   │   ├── YYYY-MM-DD_five-forces.md    # 分析結果（業界の魅力度）。レポートはこれを参照する
│   │   └── YYYY-MM-DD_five-forces.json  # 同じ結果の機械可読版（スクリプトが生成）
│   └── three-c/                 # 3C分析（three-c。180日有効）
│       ├── YYYY-MM-DD_brief.md          # 執筆の材料（スクリプトが生成）
│       ├── YYYY-MM-DD_three-c.md        # 分析結果（勝てる理由）。レポートはこれを参照する
│       └── YYYY-MM-DD_three-c.json      # 同じ結果の機械可読版（スクリプトが生成）
├── sessions/
│   └── YYYY-MM-DD_{topic}/      # 分析セッション（1回の分析につき1ディレクトリ）
│       ├── {分析ファイル群}      # 各フェーズの分析結果（スキル定義に従う）
│       └── judgment-sheet.md    # 判定シート（総合判断）
└── reports/
    └── YYYY-MM-DD_{type}.md     # 投資レポート
                                 # type: initiation（新規）/ update（更新）/ exit（撤退）
```

### 地合い分析

```
market/
├── policy/{japan,us}/           # 国家方針・財政・金融政策の文書ライブラリ（collect-market-info。新しい版だけ追加）
│   ├── index.csv                # 資料台帳（スクリプトが管理）
│   ├── sources/                 # 原本・テキスト・抜粋（git 管理外。manifest.csv だけコミット）
│   └── raw/YYYY-MM-DD_{doc_key}.md  # 文書ごとの要旨（テンプレート policy-doc / monetary-doc）
├── data/{japan,us}_series.csv   # マクロ指標・需給の時系列（スクリプトのみが書く）
└── sessions/YYYY-MM-DD_{topic}/
    ├── tasks.json               # LLM が担当するタスク一覧（prepare が生成）
    ├── status.md                # 取得結果・検証結果（スクリプトが生成）
    ├── raw/                     # 収集した生データ（分析後は変更禁止）
    │   ├── indicators-{market}.md   # マクロ指標・需給の表（スクリプトが生成）
    │   ├── calendar-{market}.md     # 政治・イベント日程と市場指標（search-calendar が記入）
    │   └── policy-digest.md         # 今回追加された文書と、監視項目ごとの最新版（スクリプトが生成）
└── report/                      # 週次の地合いレポート（market-report。{週} は出力週の月曜日）
    ├── {週}_facts.json          # レポートの数値・チャート系列・日程（スクリプトが生成）
    ├── {週}_brief.md            # 執筆の材料を1ファイルに集約したもの（スクリプトが生成）
    ├── {週}_outlook.md          # 地合い判断（強気/中立/慎重/弱気）と短期・中期・長期の展望。企業分析はこれを参照する
    └── {週}_market-report.html  # プレゼンテーション形式の単一 HTML（スクリプトが outlook.md と facts.json から生成）
```

- 地合い判断は `market/report/` の最新の `{週}_outlook.md`（FILL が残っていないもの）。過去の週の完成済み outlook.md は変更しない

- `raw/` と `policy/*/raw/` は collect-market-info のスクリプトがテンプレート（`.ai/templates/collect-market-info/`）から作る。LLM は `<!-- FILL:... -->` の欄だけを埋める
- 書き込みのルールは `tools/guard/write_guard.py`（Claude Code の PreToolUse hook）が強制する

### raw/ の扱い

- 収集したデータは **変更禁止**。誤りに気づいた場合も上書きせず、新しいセッションで再収集する
- 企業の `raw/` 配下のファイル名は `YYYY-MM-DD_{種類}.md`（収集日＋情報の種類を表す英語名）とし、再収集時も既存ファイルを上書きしない
- 収集日時をファイル冒頭に記録する（例: `収集日: 2026-10-11`）

## 分析ファイルの必須ヘッダー

各分析ファイルの冒頭に以下を記載する。

```markdown
# {分析名} — {企業名 or 対象}

**分析日**: YYYY-MM-DD
**参照資料**: {主な参照資料と期・URL}
**地合い**: {参照した outlook.md のファイル名（例: market/report/2026-10-12_outlook.md）}（地合い分析ファイルは不要）
```

## 評価の記述形式

各評価は「見るもの → 根拠（情報源） → 結論」の形式で記述する。

```markdown
## {評価項目}

**見たもの**: {数値・データの概要}
**情報源**: {URL または ファイル名・ページ番号}
**結論**: {良好/普通/懸念 など}
```

## 判定の表記

評価の結論は以下の表記に統一する。

| 区分 | 使用する表記 |
|---|---|
| 事業・競争環境分析の判定 | `A` / `B` / `C` |
| 財務分析の各項目 | `良好` / `普通` / `懸念` |
| バリュエーションの各指標 | `割安` / `妥当` / `割高` / `評価対象外` |
| 地合い判断 | `強気` / `中立` / `慎重` / `弱気` |
| 総合判断 | `投資検討` / `ウォッチ` / `見送り` |

## 数値の表記

- パーセント: 小数点1桁まで（例: `12.3%`）
- 倍率: 小数点1桁まで（例: `15.2倍`）
- 金額: 単位を明記（例: `1,234百万円`、`$1.2B`）
- CAGR: 小数点1桁まで（例: `年率5.4%`）
- 不明・未取得: `—`（ダッシュ）で表記。空欄にしない

## セッション完了時の確認事項

- [ ] 全分析ファイルに情報源が記載されているか
- [ ] 判定シートの全項目が記入されているか
- [ ] `overview.md` の更新日・判断・次回見直し日が更新されているか
