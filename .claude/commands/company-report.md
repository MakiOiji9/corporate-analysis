---
description: 企業分析レポート。企業分析フレームワーク.md の STEP 1〜3（five-forces・three-c・moat・swot・profitability・growth・safety・cash-flow・valuation）を依存の順に実行し（鮮度が新しい分析はスキップ）、STEP 1・2 の総合判定（A/B/C）と判定マトリクスから短期（〜3ヶ月）・中期（6ヶ月〜1年）・長期（3年以上）の判定（投資検討/ウォッチ/見送り/判定保留）を根拠つきで出し、株価の過去レンジ（52週・3年・5年・10年）と合わせて、初心者からプロまで読める日付付きの単一 HTML（companies/{ticker}_{name}/reports/{日付}_company-report.html）にまとめる。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/prompts/company-report.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `not_fresh` が多い企業・レポートが古い企業を優先して4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明に、新しくない分析（`not_fresh`）と最新のレポートの日付・状態を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `next` がスキル名（`five-forces`・`three-c`・`moat`・`swot`・`profitability`・`growth`・`safety`・`cash-flow`・`valuation`・`market-report`）のときは、Skill ツールでそのスキルを起動する（引数は `{ticker}`。market-report は引数なし）。その手順書を最後の完了報告まで実行してから、このコマンドの手順 1 に戻る。スキルの完了報告はユーザーにそのまま見せてよいが、このコマンドの完了報告にも要点をまとめる
- 同じスキルを1回の実行で2回起動しない。2回目に `next` に出たら止まって報告する
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/report/company_report.py check --company {company}` のように実行する
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで company-report.md を Edit する。Edit は欄ごとに1回
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
