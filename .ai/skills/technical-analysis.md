# テクニカル分析スキル（technical-analysis）

企業分析レポートの「テクニカル分析（切り口別）」章の材料を、日々の株価（`companies/{ticker}_{name}/data/prices.csv`）から作る。
トレンド・モメンタム・ボラティリティ・出来高・水準・チャートパターン（三尊・ダブルトップなど）・総合（強気/基本/弱気の3シナリオ）を、日足と週足（日足から集計）で別々に出す。
**数値・判定・文章の素材はすべて Python が出す。LLM が書く欄は無い。**

- 成果物: `companies/{ticker}_{name}/analysis/technical/technical.json`（機械可読。`generated_at`・`price_asof`・日足と週足の各切り口）と `technical.md`（読み物）
- 再分析の条件は**終値の更新だけ**（時間の期限は無い）。`price_asof`（使った最新の確定終値の日付）より新しい終値が `prices.csv` にあるとき、またはロジックの版（`cr_tech_cache.VERSION`）が変わったときに作り直し、同じなら再利用する
- 点数に入るのは**日足の「トレンド」切り口だけ**で、短期の「株価のテクニカル（日足のトレンド）」になる（上昇 +1・もみ合い 0・下降 −1、確度「低」は 0。判定ルールの改定 3）。ほかの切り口は点数に入れない。中期は `cr_technicals.py` の点数のまま。予想・推奨ではなく、条件つきの目安
- 章の固定の注意書き（予想であり確実でない・形成中は確定でない・過去の的中は保証でない）は HTML 生成側（`tools/report/cr_ch_tech.py`）が必ず出す

## 手順

1. 株価が古ければ `python -I tools/collect/stock_prices.py` で取り直す（`company_report.py prepare` が自動で行う）
2. `python -I tools/report/company_report.py technical --company {company} [--redo] [--skip-prices]` を実行する
3. 出力の `price_asof`・`reused`・`alignment`（日足と週足の向きの一致）をユーザーに伝える

`/company-report` の `prepare` は同じ分析を自動で呼ぶので、通常はこのスキルを単独で使う必要は無い。

## チャートパターン

`tools/report/cr_patterns.py` が終値から転換点（ジグザグ）を作り、幾何条件で判定する。状態は 形成中・完成・失敗 の3段階で、目標値と無効化ラインを併記する。
閾値を 0.8 倍・1.25 倍に変えても同じ形が出るかを確かめ（安定/不安定）、同銘柄の過去の同じ形の後の値動きを実績で添える（5件未満は「参考値」）。
