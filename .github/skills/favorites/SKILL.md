---
name: favorites
description: お気に入り企業の管理スキル。企業分析レポートを GitHub Actions で平日に定期実行する企業を、管理台帳 companies/favorites.json の A グループ（0:30 JST）・B グループ（6:00 JST）に追加・削除・付け替えする（各グループ5社まで、企業分析レポートを一度も build していない企業は登録できない）。台帳の読み書きはすべて tools/report/favorites.py が行い、台帳の手修正は禁止。お気に入りに追加・削除したいとき、定期実行の対象企業を確かめたいときに使う。
---

`.ai/skills/favorites.md` を読み、その手順に厳密に従って実行する。

操作（add・remove・move・list）・企業・グループはユーザーの依頼文から読み取る。グループが省略された場合は推測せずユーザーに確かめる。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。このスキルで編集してよいファイルは無い。`companies/favorites.json` は `favorites.py` だけが書く（手で直すと digest の不一致でワークフローが止まる）。

```
python -I tools/guard/write_guard.py --check companies/favorites.json
```
