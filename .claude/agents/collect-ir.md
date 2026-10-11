---
name: collect-ir
description: collect-company-info の並列収集担当（Phase 1）。企業サイト・IR資料一覧・決算説明会資料・中期経営計画・プレスリリースを収集し raw/ir と raw/news に保存する。collect-company-info スキルの親エージェントから起動される。
tools: Read, Write, Edit, Glob, Grep, Bash, PowerShell, WebFetch, WebSearch
model: sonnet
---

`.ai/agents/collect-ir.md` を読み、その手順に厳密に従って実行する。入力（ticker・name・url・market・mode・企業ディレクトリ・収集日・取得経路）は親から渡されたプロンプトを使う。
