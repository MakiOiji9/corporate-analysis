---
name: market-report
description: 地合いレポート作成スキル。collect-market-info が集めた日米の時系列・指標・日程・政策文書の要旨を統合し、市場動向と短期・中期・長期の展望をまとめたプレゼンテーション形式の単一 HTML（market/report/{週の月曜}_market-report.html）と、企業分析が参照する地合い判断 outlook.md を作る。材料が今週の収集でなければ先に collect-market-info を実行する。週次の地合いレポートが欲しいとき、日米の市場動向や地合い判断（強気/中立/慎重/弱気）をまとめたいときに使う。
argument-hint: "[week=YYYY-MM-DD] [redo]"
---

`.ai/skills/market-report.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 1 で `fresh: false` のときは、Skill ツールで `collect-market-info` を引数 `both topic=weekly` で起動し、その手順書（並列モード）を最後の finalize まで実行してから、このスキルの手順 1 に戻る
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで outlook.md を Edit する（日米を一人の書き手が通して書く）
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
