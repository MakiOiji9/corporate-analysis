---
name: five-forces
description: ファイブフォース分析スキル。企業分析フレームワーク.md の STEP 1-1（新規参入・代替品・買い手・売り手・業界内競争の5要因を 強/中/弱 で評価し、業界の魅力度 高/中/低 を判定）を、collect-company-info・collect-market-info・market-report が集めた材料から行い、companies/{ticker}_{name}/analysis/five-forces/ に Markdown と JSON で保存する。結果は365日有効で、期間内は再分析しない（新しい有報・業界・競合の収集があれば再分析）。材料が足りなければ収集スキルを先に実行する。業界の魅力度・ファイブフォースを分析したいとき、企業分析の STEP 1 を始めるときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/five-forces.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `five_forces` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明に状態・分析日・魅力度・最終収集日を書く
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `market_report` のときは、Skill ツールで `market-report` を引数なしで起動し、その手順書を最後まで実行してから、このスキルの手順 1 に戻る
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで five-forces.md を Edit する（5要因を一人の書き手が通して書く）
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
