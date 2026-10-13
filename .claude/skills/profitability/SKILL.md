---
name: profitability
description: 収益性分析スキル。企業分析フレームワーク.md の STEP 2-1（収益性: ROE の5〜10年の水準と安定性、営業利益率の同業比較、ROE を売上高純利益率・総資産回転率・財務レバレッジに分解した源泉（本業由来/借入依存）から 収益性 良好/普通/懸念（材料不足なら判定保留） を判定）を、collect-company-info が集めた財務時系列・有報・競合の材料から行い、companies/{ticker}_{name}/analysis/profitability/ に Markdown と JSON で保存する。数値の計算と判定はすべて Python スクリプトが行い、LLM は数値の背景と引き継ぎだけを書く。結果は180日有効で、期間内は再分析しない（新しい決算期・財務時系列・競合の収集や新しいモート・3C分析があれば再分析）。材料が足りなければ collect-company-info を先に実行する。STEP 1 は前提にせず、モート・3C の結果があれば整合性チェックに使う。ROE・デュポン分解・収益性・STEP 2 の財務分析を始めたいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/profitability.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `profitability` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明に収益性の状態・分析日・結論・モートと3Cの結論・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/analysis/profitability.py check --company {company}` のように実行する
- collect-company-info を起動するときに、raw の書き方（範囲外の章の扱い・再掲）を引数やプロンプトで指定しない
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで profitability.md を Edit する。Edit は欄ごとに1回
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
