---
name: moat
description: モート分析スキル。企業分析フレームワーク.md の STEP 1-3（経済的な堀。ブランド・スイッチングコスト・ネットワーク効果・コスト優位・規制/特許/許認可の該当を判定し、営業利益率の同業比較（最大10年）とシェアの推移で裏付け、崩しうる要因から持続性を見て、モート 広い/狭い/なし（材料不足なら判定保留） を判定）を、collect-company-info・collect-market-info・market-report が集めた材料と3C・ファイブフォースの結果から行い、companies/{ticker}_{name}/analysis/moat/ に Markdown と JSON で保存する。結果は180日有効で、期間内は再分析しない（新しい有報・財務・事業概要・業界・競合の収集や新しい3C分析があれば再分析）。3Cが未実施なら先に three-c、材料が足りなければ収集スキルを実行する。強みの持続性・経済的な堀・モートを分析したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/moat.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `moat` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明にモートの状態・分析日・結論・3Cの状態・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `three_c` のときは、Skill ツールで `three-c` を起動する。引数は `{dir}`（3Cが `fresh` 以外なので再分析される）。その手順書を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/analysis/moat.py check --company {company}` のように実行する
- collect-company-info を起動するときに、raw の書き方（範囲外の章の扱い・再掲）を引数やプロンプトで指定しない
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで moat.md を Edit する（モートの特定・裏付け・持続性を一人の書き手が通して書く）。Edit は章・表ごとに1回
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
