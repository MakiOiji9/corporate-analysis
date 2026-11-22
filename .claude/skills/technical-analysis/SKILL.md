---
name: technical-analysis
description: テクニカル分析スキル。日々の株価から、トレンド・モメンタム・ボラティリティ・出来高・水準・チャートパターン（三尊・ダブルトップ・三角持ち合いなど）・総合（強気/基本/弱気の3シナリオ）を日足と週足で分析し、companies/{ticker}_{name}/analysis/technical/ に json と md で保存する。再分析は終値が更新されたときだけ（時間の期限は無い）。数値と文章の素材はすべて Python が出し、点数（短期・中期の判定）には入れない。企業分析レポートの「テクニカル分析」章の材料になる（/company-report の prepare が自動で呼ぶ）。チャートの形や今後の動きの条件を単独で確認したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]"
---

`.ai/skills/technical-analysis.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 企業が省略されたときは companies/ のディレクトリ名から AskUserQuestion で選ぶ（企業が1社だけなら聞かずに進む）
- スクリプトは `python -I tools/report/company_report.py technical --company {company}`。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I ...` として実行する
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
