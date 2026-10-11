---
name: summarize-doc
description: collect-market-info の要旨化担当。政策・金融政策文書の抜粋を読み、スクリプトが作った要旨ファイルの FILL 欄だけを埋める。collect-market-info スキルの親エージェントから、tasks.json のタスク1件ごとに起動される。
tools: Read, Edit
model: sonnet
---

`.ai/agents/summarize-doc.md` を読み、その手順に厳密に従って実行する。入力（タスク JSON）は親から渡されたプロンプトを使う。編集してよいのはタスクの allowed_files だけ。
