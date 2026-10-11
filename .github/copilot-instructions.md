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

## ツールと初回セットアップ

情報収集用の Python スクリプトは `tools/collect/`（地合い用は `tools/collect/market/`）にある。使い方とセットアップは `tools/README.md` を参照。

Copilot には書き込み hook が無いため、collect-market-info の実行中は、ファイルを編集する前に `python -I tools/guard/write_guard.py --check <path>` を実行し、`BLOCKED` なら編集しない。

## 言語ポリシー

- 応答: 日本語
- ファイル名・ディレクトリ名: 英語
- 分析コンテンツ（ファイルの中身）: 日本語
