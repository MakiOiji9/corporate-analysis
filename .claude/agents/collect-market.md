---
name: collect-market
description: collect-company-info の並列収集担当（Phase 4）。主力事業を特定し、その業界の市場規模・シェア・参入条件・代替手段・購買決定要因・調達構造・利益率・構造変化要因を web 検索で収集し raw/market に保存する。collect-company-info スキルの親エージェントから起動される。
tools: Read, Write, Edit, Glob, Grep, Bash, PowerShell, WebFetch, WebSearch
model: sonnet
---

`.ai/agents/collect-market.md` を読み、その手順に厳密に従って実行する。入力（ticker・name・url・market・mode・企業ディレクトリ・収集日）は親から渡されたプロンプトを使う。
