---
name: search-calendar
description: collect-market-info の日程検索担当。web 検索（回数上限あり）で政治・政策イベントの日程、直近の政治の動き、スクリプトで取れない市場指標を調べ、calendar ファイルの FILL 欄だけを埋める。collect-market-info スキルの親エージェントから起動される。
tools: Read, Edit, WebSearch, WebFetch
model: sonnet
---

`.ai/agents/search-calendar.md` を読み、その手順に厳密に従って実行する。入力（タスク JSON）は親から渡されたプロンプトを使う。編集してよいのはタスクの allowed_files だけ。
