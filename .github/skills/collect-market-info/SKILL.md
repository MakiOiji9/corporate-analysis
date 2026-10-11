---
name: collect-market-info
description: 地合い情報収集スキル。日本・米国の国家方針（所信表明・施政方針演説、骨太の方針、エネルギー基本計画、大統領令など）、財政・税制、金融政策（日銀・FOMC）の文書、マクロ指標・市場需給の時系列、政治・イベント日程を収集し、market/ 配下（文書ライブラリ policy/、時系列 data/、セッション sessions/）に保存する。収集の大部分は Python スクリプトが行い、LLM は文書の要旨化と日程検索だけを行う。地合い分析の前に材料を集めたいとき、最新の政策・指標に更新したいときに使う。
---

`.ai/skills/collect-market-info.md` を読み、その手順に厳密に従って実行する。

引数（market・topic・mode）はユーザーの依頼文から読み取る。省略された場合は手順書の既定値を使い、その旨をユーザーに伝える。

## GitHub Copilot での実行方法

- 手順書の**逐次モード**で実行する。タスク（`tasks.json`）を上から順に、`type` に応じた手順書（`.ai/agents/summarize-doc.md` / `.ai/agents/search-calendar.md`）に従って自分で処理する
- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 1タスクを終えるごとに、そのタスクで使った抜粋・検索結果の内容は次のタスクに持ち越さない（要旨は出力ファイルにだけ書く）

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- 編集してよいのはタスクの `allowed_files` に載ったファイルの `<!-- FILL:... -->` 行だけ。ファイルの新規作成・上書き（全体の書き換え）はしない
- 最後の `finalize` が、範囲外の変更（`out_of_scope`）とテンプレートとの違いを検出する。指摘が出たら、自分で戻さずユーザーに報告する
