---
name: collect-company-info
description: 企業情報収集スキル。対象企業のホームページURLを起点に、IR資料・有価証券報告書/10-K・財務時系列・業界/競合・株価指標を収集し、companies/{ticker}_{name}/ 配下に生データ(raw/)と要約(summaries/)を保存する。企業分析の前に情報を集めたいとき、銘柄コード・企業名・ホームページURLを示して情報収集を依頼されたときに使う。
---

`.ai/skills/collect-company-info.md` を読み、その手順に厳密に従って実行する。

引数（ticker・name・url・market）はユーザーの依頼文から読み取る。不足している場合は収集を始める前にユーザーに確認する。
