---
name: three-c
description: 3C分析スキル。企業分析フレームワーク.md の STEP 1-2（顧客・競合・自社を分析し、顧客の KBF・市場の成長性・競合との比較 優位/同等/劣位・KBF ごとの自社と競合の比較から、勝てる理由 明確/あいまい/なし を判定）を、collect-company-info・collect-market-info・market-report が集めた材料とファイブフォースの結果から行い、companies/{ticker}_{name}/analysis/three-c/ に Markdown と JSON で保存する。結果は180日有効で、期間内は再分析しない（新しい有報・事業概要・業界・競合の収集や新しいファイブフォース分析があれば再分析）。ファイブフォースが未実施なら先に five-forces、材料が足りなければ収集スキルを実行する。会社の立ち位置・勝てる理由・3C を分析したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/three-c.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `three_c` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明に3Cの状態・分析日・結論・ファイブフォースの状態・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `five_forces` のときは、Skill ツールで `five-forces` を起動する。引数は `{dir}`（ファイブフォースが `fresh` 以外なので再分析される）。その手順書を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで three-c.md を Edit する（顧客・競合・自社を一人の書き手が通して書く）。Edit は章・表ごとに1回
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
