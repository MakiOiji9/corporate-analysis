---
name: collect-company-info
description: 企業情報収集スキル。対象企業のホームページURLを起点に、IR資料・有価証券報告書/10-K・財務時系列・業界/競合・株価指標を収集し、companies/{ticker}_{name}/ 配下に原本(sources/)・構造化データ(data/)・生データ(raw/)・要約(summaries/)を保存する。mode=update で前回以降の差分だけを更新する。企業分析の前に情報を集めたいとき、既存企業の情報を最新化したいとき、銘柄コード・企業名・ホームページURL（URLだけでも可）を示して依頼されたときに使う。
argument-hint: "{ticker} {name} {url} {japan|us} [mode=full|update]  ※URLだけでも可"
---

`.ai/skills/collect-company-info.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS
