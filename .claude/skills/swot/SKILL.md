---
name: swot
description: SWOT分析スキル。企業分析フレームワーク.md の STEP 1-4（1-1〜1-3 の結果と中期経営計画・事業等のリスク・業界・地合いの事実を 強み/弱み/機会/脅威 に振り分け、影響度 大/中/小 を評価し、最大の強みで最大の脅威に対抗できるかを SWOT Yes/条件付き/No（材料不足なら判定保留） で判定）を、collect-company-info・collect-market-info・market-report が集めた材料とファイブフォース・3C・モートの結果から行い、companies/{ticker}_{name}/analysis/swot/ に Markdown と JSON で保存する。結果は180日有効で、期間内は再分析しない（新しい有報・中期経営計画・事業概要・業界の収集や新しい上流の分析があれば再分析）。モートが未実施なら先に moat、地合いが古ければ market-report、材料が足りなければ collect-company-info を実行する。SWOT・STEP 1 の総括・最大の強みと脅威を分析したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/swot.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `swot` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明に SWOT の状態・分析日・結論・モートの状態・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `moat` のときは、Skill ツールで `moat` を起動する。引数は `{dir}`。その手順書を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `market_report` のときは、Skill ツールで `market-report` を起動する（引数なし）。その手順書を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/analysis/swot.py check --company {company}` のように実行する
- collect-company-info を起動するときに、raw の書き方（範囲外の章の扱い・再掲）を引数やプロンプトで指定しない
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで swot.md を Edit する（4象限・影響度・判定を一人の書き手が通して書く）。Edit は章・表ごとに1回
- 上流のスキル（moat・market-report・collect-company-info）の作業で読んだ raw・抜粋・検索結果は、SWOT の執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
