# Claude Code 共通指示

このリポジトリは日本株・米国株の投資判断を支援するための企業分析・地合い分析リポジトリです。

## 必ず従う指示

作業前に以下を読み、遵守してください。

- `.ai/instructions/role.md` — AIの役割
- `.ai/instructions/policy.md` — 行動指針と禁止事項
- `.ai/instructions/output-format.md` — 出力形式・ディレクトリ構造

## スキル

スキルの実体は `.ai/skills/` にあり、`.claude/skills/` はそれを参照するエントリーポイントです。
サブエージェントも同様に、実体は `.ai/agents/`、エントリーポイントは `.claude/agents/` です（collect-company-info の並列収集担当 `collect-ir` / `collect-filings` / `collect-market` / `collect-peers-valuation`、collect-market-info のタスク担当 `summarize-doc` / `search-calendar`）。

| スキル | 用途 | 依頼に含める情報 |
|---|---|---|
| `collect-company-info` | 企業情報収集（原本・構造化データ・生データ・要約の保存、`mode=update` で差分更新） | 銘柄コード・企業名（英語）・ホームページURL・市場（japan / us）。URL だけでも可 |
| `collect-market-info` | 地合い情報収集（国家方針・財政・金融政策の文書、マクロ指標・需給の時系列、政治・イベント日程） | 市場（japan / us / both）。省略可 |
| `market-report` | 週次の地合いレポート（日米の市場動向と短期・中期・長期の展望。単一 HTML と outlook.md を `market/report/` に出力。材料が古ければ先に collect-market-info を実行） | 出力週（YYYY-MM-DD）。省略可 |
| `five-forces` | ファイブフォース分析（業界の魅力度 高/中/低。`companies/{ticker}_{name}/analysis/five-forces/` に md と json。365日有効で期間内は再分析しない。材料が足りなければ collect-company-info を先に実行。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `three-c` | 3C分析（顧客・競合・自社から勝てる理由 明確/あいまい/なし（材料不足なら判定保留）。`companies/{ticker}_{name}/analysis/three-c/` に md と json。180日有効で期間内は再分析しない。ファイブフォースが未実施なら先に five-forces、材料が足りなければ collect-company-info を実行。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `moat` | モート分析（5種のモートの該当、営業利益率の同業比較とシェアの推移による裏付け、崩しうる要因から モート 広い/狭い/なし（材料不足なら判定保留）。`companies/{ticker}_{name}/analysis/moat/` に md と json。180日有効で期間内は再分析しない。3Cが未実施なら先に three-c（3Cの結論では止めない）、材料が足りなければ collect-company-info を実行。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `swot` | SWOT分析（1-1〜1-3 の結果と中計・事業等のリスク・業界・地合いの事実を4象限に振り分け、影響度 大/中/小 から最大の強みで最大の脅威に対抗できるかを SWOT Yes/条件付き/No（材料不足なら判定保留）で判定。`companies/{ticker}_{name}/analysis/swot/` に md と json。180日有効で期間内は再分析しない。モートが未実施なら先に moat（上流の結論では止めない）、地合いの outlook.md が無い・古ければ market-report、材料が足りなければ collect-company-info を実行。STEP 1 判定（A/B/C）はしない） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `profitability` | 収益性分析（STEP 2-1。ROE の水準と安定性・営業利益率の同業比較・デュポン分解による源泉から 収益性 良好/普通/懸念（材料不足なら判定保留）。数値と判定は Python が出し、LLM は背景だけを書く。`companies/{ticker}_{name}/analysis/profitability/` に md と json。180日有効で期間内は再分析しない。材料が足りなければ collect-company-info を実行。STEP 1 は前提にせず、モート・3C の結果があれば整合性チェックに使う。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `growth` | 成長性分析（STEP 2-2。売上・営業利益・EPS の CAGR、減収・減益の年の原因（一時/構造）、期初予想の達成率による計画の信頼性、成長の質（利益率・M&A・自社株買い）から 成長性 良好/普通/懸念（材料不足なら判定保留）。数値と判定は Python が出し、LLM は減収・減益の年の分類と背景だけを書く。`companies/{ticker}_{name}/analysis/growth/` に md と json。180日有効で期間内は再分析しない。材料が足りなければ collect-company-info を実行。STEP 1 は前提にせず、3C の市場の成長性・SWOT の弱み/脅威があれば整合性チェックと構造要因の照合に使う。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `cash-flow` | キャッシュフロー分析（STEP 2-4。営業CF の安定性・FCF の創出力・営業CF対純利益比率による利益の質・CF パターン・株主還元の持続性から キャッシュフロー 良好/普通/懸念（材料不足なら判定保留）。「一時要因」「成長投資期」は数値の代理指標で判定。数値と判定は Python が出し、LLM は背景だけを書く。`companies/{ticker}_{name}/analysis/cash-flow/` に md と json。180日有効で期間内は再分析しない。材料が足りなければ collect-company-info を実行。同業比較・STEP 1 は使わず、収益性・成長性・安全性分析の結果があれば整合性チェックに使う。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |
| `safety` | 安全性分析（STEP 2-3。自己資本比率・D/E レシオ・流動比率を目安と同業平均で判定し、ネットキャッシュがプラスなら実質無借金、5年の推移で悪化傾向、有利子負債が増えた年の CF で借入の目的を見て 安全性 良好/普通/懸念（材料不足なら判定保留）。数値と判定は Python が出し、LLM は背景だけを書く。`companies/{ticker}_{name}/analysis/safety/` に md と json。180日有効で期間内は再分析しない。材料が足りなければ collect-company-info を実行。STEP 1・収益性は前提にせず、収益性の結果と地合いの outlook.md の金利の行は brief に引用するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |

| `valuation` | バリュエーション分析（STEP 3。PER・PBR・PEG・EV/EBITDA を過去5年レンジでの位置と同業中央値との差の共通ルールで 割安/妥当/割高/評価対象外 に判定し、点数の平均と STEP 2・SWOT による最終確認で STEP 3 割安/妥当/割高（材料不足なら判定保留）。数値と判定は Python が出し、LLM は背景と、PBR のバリュートラップのときの改善策の有無だけを書く。`companies/{ticker}_{name}/analysis/valuation/` に md と json。株価が動くため7日有効で、株価の基準日が7日より古ければ collect-company-info で株価を取り直す。成長性分析が未実施なら先に growth（成長性の結論では止めない）。収益性・安全性・キャッシュフロー・SWOT の結果は最終確認にだけ使う。地合いの outlook.md は参照するだけ） | 銘柄コード・企業ディレクトリ名・社名の一部。省略時は一覧から選択 |

## ツールと初回セットアップ

情報収集用の Python スクリプトは `tools/collect/`（地合い用は `tools/collect/market/`）、レポート作成用は `tools/report/` にある。使い方とセットアップは `tools/README.md` を参照。
設定はすべてこのリポジトリ内で完結する（`.venv`、`.env`、`.claude/settings.json`）。
`.claude/settings.json` の PreToolUse hook（`tools/guard/write_guard.py`）が、スクリプト専用ファイルの手書き・完成済み raw の変更・スキル実行中の範囲外の書き込みをブロックする。

## 言語ポリシー

- 応答: 日本語
- ファイル名・ディレクトリ名: 英語
- 分析コンテンツ（ファイルの中身）: 日本語
