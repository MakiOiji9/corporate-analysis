---
name: collect-market-info
description: 地合い情報収集スキル。日本・米国の国家方針（所信表明・施政方針演説、骨太の方針、エネルギー基本計画、大統領令など）、財政・税制、金融政策（日銀・FOMC）の文書、マクロ指標・市場需給の時系列、政治・イベント日程を収集し、market/ 配下（文書ライブラリ policy/、時系列 data/、セッション sessions/）に保存する。収集の大部分は Python スクリプトが行い、LLM は文書の要旨化と日程検索だけをサブエージェントで並列に行う。地合い分析の前に材料を集めたいとき、最新の政策・指標に更新したいときに使う。
argument-hint: "[japan|us|both] [topic=weekly] [mode=full|update]"
---

`.ai/skills/collect-market-info.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS
