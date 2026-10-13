# GitHub Copilot 共通指示

このリポジトリは日本株・米国株の投資判断を支援するための企業分析・地合い分析リポジトリです。

## 必ず従う指示

作業前に以下を読み、遵守してください。

- `.ai/instructions/role.md` — AIの役割
- `.ai/instructions/policy.md` — 行動指針と禁止事項
- `.ai/instructions/output-format.md` — 出力形式・ディレクトリ構造

## スキル

スキルの実体は `.ai/skills/` にあり、`.github/skills/` はそれを参照するエントリーポイントです。

| スキル | 用途 | 依頼に含める情報 |
|---|---|---|
| `collect-company-info` | 企業情報収集（原本・構造化データ・生データ・要約の保存、`mode=update` で差分更新） | 銘柄コード・企業名（英語）・ホームページURL・市場（japan / us）。URL だけでも可 |
| `collect-market-info` | 地合い情報収集（国家方針・財政・金融政策の文書、マクロ指標・需給の時系列、政治・イベント日程） | 市場（japan / us / both）。省略可 |
| `market-report` | 週次の地合いレポート（日米の市場動向と短期・中期・長期の展望。単一 HTML と outlook.md を `market/report/` に出力。材料が古ければ先に collect-market-info を実行） | 出力週（YYYY-MM-DD）。省略可 |
| `five-forces` | ファイブフォース分析（業界の魅力度 高/中/低。`companies/{ticker}_{name}/analysis/five-forces/` に md と json。365日有効で期間内は再分析しない。材料が足りなければ collect-company-info を先に実行。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `three-c` | 3C分析（顧客・競合・自社から勝てる理由 明確/あいまい/なし（材料不足なら判定保留）。`companies/{ticker}_{name}/analysis/three-c/` に md と json。180日有効で期間内は再分析しない。ファイブフォースが未実施なら先に five-forces、材料が足りなければ collect-company-info を実行。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `moat` | モート分析（5種のモートの該当、営業利益率の同業比較とシェアの推移による裏付け、崩しうる要因から モート 広い/狭い/なし（材料不足なら判定保留）。`companies/{ticker}_{name}/analysis/moat/` に md と json。180日有効で期間内は再分析しない。3Cが未実施なら先に three-c（3Cの結論では止めない）、材料が足りなければ collect-company-info を実行。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `swot` | SWOT分析（1-1〜1-3 の結果と中計・事業等のリスク・業界・地合いの事実を4象限に振り分け、影響度 大/中/小 から最大の強みで最大の脅威に対抗できるかを SWOT Yes/条件付き/No（材料不足なら判定保留）で判定。`companies/{ticker}_{name}/analysis/swot/` に md と json。180日有効で期間内は再分析しない。モートが未実施なら先に moat（上流の結論では止めない）、地合いの outlook.md が無い・古ければ market-report、材料が足りなければ collect-company-info を実行。STEP 1 判定（A/B/C）はしない） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |

## ツールと初回セットアップ

情報収集用の Python スクリプトは `tools/collect/`（地合い用は `tools/collect/market/`）、レポート作成用は `tools/report/` にある。使い方とセットアップは `tools/README.md` を参照。

Copilot には書き込み hook が無いため、collect-market-info・market-report・five-forces・three-c・moat・swot の実行中は、ファイルを編集する前に `python -I tools/guard/write_guard.py --check <path>` を実行し、`BLOCKED` なら編集しない。

## 言語ポリシー

- 応答: 日本語
- ファイル名・ディレクトリ名: 英語
- 分析コンテンツ（ファイルの中身）: 日本語
