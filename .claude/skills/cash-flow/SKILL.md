---
name: cash-flow
description: キャッシュフロー分析スキル。企業分析フレームワーク.md の STEP 2-4（キャッシュフロー: 営業CF の5〜10年の安定性、FCF（営業CF＋投資CF）の5年累計と創出力、営業CF対純利益比率による利益の質（売上債権・棚卸資産の増加率も確認）、営業・投資・財務CF の符号パターン、株主還元と FCF の比較から キャッシュフロー 良好/普通/懸念（材料不足なら判定保留） を判定）を、collect-company-info が集めた財務時系列・有報の材料から行い、companies/{ticker}_{name}/analysis/cash-flow/ に Markdown と JSON で保存する。数値の計算と判定はすべて Python スクリプトが行い、LLM は数値の背景と引き継ぎだけを書く。結果は180日有効で、期間内は再分析しない（新しい決算期・財務時系列の収集や新しい収益性分析があれば再分析）。材料が足りなければ collect-company-info を先に実行する。同業比較・STEP 1 は使わず、収益性・成長性・安全性分析の結果があれば整合性チェックに使う。手順3が懸念なら純利益と営業CF の差の内訳と主因も示す。営業CF・FCF・利益の質・キャッシュフローを分析したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/cash-flow.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `cash_flow` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明にキャッシュフローの状態・分析日・結論・収益性の結論・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/analysis/cash_flow.py check --company {company}` のように実行する
- collect-company-info を起動するときに、raw の書き方（範囲外の章の扱い・再掲）を引数やプロンプトで指定しない
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで cash-flow.md を Edit する。Edit は欄ごとに1回
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
