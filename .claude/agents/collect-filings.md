---
name: collect-filings
description: collect-company-info の並列収集担当（Phase 2・3）。有価証券報告書/10-K、財務時系列（5〜10年）、期初予想と実績、直近四半期をスクリプト中心に収集し raw/filings・raw/ir・data に保存する。collect-company-info スキルの親エージェントから起動される。
tools: Read, Write, Edit, Glob, Grep, Bash, PowerShell, WebFetch, WebSearch
model: sonnet
---

`.ai/agents/collect-filings.md` を読み、その手順に厳密に従って実行する。入力（ticker・name・url・market・mode・企業ディレクトリ・収集日・取得経路）は親から渡されたプロンプトを使う。
