---
name: growth
description: 成長性分析スキル。企業分析フレームワーク.md の STEP 2-2（成長性: 売上高・営業利益・EPS の5〜10年の CAGR（EPS は株式分割を調整）、減収・減益の年の原因（一時/構造）と回復、期初予想に対する達成率による会社計画の信頼性、成長の質（利益が売上以上に伸びているか・M&A 頼みでないか・自社株買い頼みでないか）から 成長性 良好/普通/懸念（材料不足なら判定保留） を判定）を、collect-company-info が集めた財務時系列・有報・中期経営計画の材料から行い、companies/{ticker}_{name}/analysis/growth/ に Markdown と JSON で保存する。数値の計算と判定はすべて Python スクリプトが行い、LLM は減収・減益の年の分類と数値の背景・引き継ぎだけを書く。結果は180日有効で、期間内は再分析しない（新しい決算期・財務時系列・中期経営計画の収集や新しい 3C・SWOT 分析があれば再分析）。材料が足りなければ collect-company-info を先に実行する。STEP 1 は前提にせず、3C の市場の成長性と SWOT の弱み・脅威があれば整合性チェックと構造要因の照合に使う。地合いの outlook.md は参照するだけ。売上成長・CAGR・EPS 成長・計画達成率・成長性を分析したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/growth.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `growth` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明に成長性の状態・分析日・結論・3C の市場の成長性と SWOT の結論・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/analysis/growth.py check --company {company}` のように実行する
- collect-company-info を起動するときに、raw の書き方（範囲外の章の扱い・再掲）を引数やプロンプトで指定しない
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで growth.md を Edit する。Edit は欄ごとに1回（2章は1行ごとに1回）
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
