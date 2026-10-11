---
name: collect-peers-valuation
description: collect-company-info の並列収集担当（Phase 5・6）。同業他社2〜3社の選定と財務・株価指標、自社の株価・PER/PBR の過去レンジ・期末後のコーポレートアクションを収集し raw/market と raw/ir に保存する。collect-company-info スキルの親エージェントから起動される。
tools: Read, Write, Edit, Glob, Grep, Bash, PowerShell, WebFetch, WebSearch
model: sonnet
---

`.ai/agents/collect-peers-valuation.md` を読み、その手順に厳密に従って実行する。入力（ticker・name・url・market・mode・企業ディレクトリ・収集日・update 時の範囲）は親から渡されたプロンプトを使う。
