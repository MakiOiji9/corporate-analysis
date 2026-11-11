---
name: favorites
description: お気に入り企業の管理スキル。企業分析レポートを GitHub Actions で平日に定期実行する企業を、管理台帳 companies/favorites.json の A グループ（0:30 JST）・B グループ（6:00 JST）に追加・削除・付け替えする（各グループ5社まで、企業分析レポートを一度も build していない企業は登録できない）。台帳の読み書きはすべて tools/report/favorites.py が行い、台帳の手修正は禁止。お気に入りに追加・削除したいとき、定期実行の対象企業を確かめたいときに使う。
argument-hint: "[add|remove|move|list] [{銘柄コード|企業ディレクトリ名|社名の一部} ...] [A|B]  ※省略時は一覧"
---

`.ai/skills/favorites.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 2・3 でユーザーに確かめるとき（グループの指定が無い・候補が複数・上限）は AskUserQuestion で選択肢を出す
- スクリプトは1コマンドずつ実行する。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/report/favorites.py list` のように実行する
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
