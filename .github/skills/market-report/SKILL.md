---
name: market-report
description: 地合いレポート作成スキル。collect-market-info が集めた日米の時系列・指標・日程・政策文書の要旨を統合し、市場動向と短期・中期・長期の展望をまとめたプレゼンテーション形式の単一 HTML（market/report/{週の月曜}_market-report.html）と、企業分析が参照する地合い判断 outlook.md を作る。材料が今週の収集でなければ先に collect-market-info を実行する。週次の地合いレポートが欲しいとき、日米の市場動向や地合い判断をまとめたいときに使う。
---

`.ai/skills/market-report.md` を読み、その手順に厳密に従って実行する。

引数（week・redo）はユーザーの依頼文から読み取る。省略された場合は手順書の既定値を使い、その旨をユーザーに伝える。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 1 で `fresh: false` のときは、`.github/skills/collect-market-info/SKILL.md` と `.ai/skills/collect-market-info.md` を読み、collect-market-info を `market=both topic=weekly` の**逐次モード**で finalize まで実行してから、このスキルの手順 1 に戻る。収集のタスクで読んだ抜粋や検索結果は、レポートの執筆に持ち込まない（執筆は brief.md だけを根拠にする）

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `market/report/{週}_outlook.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `facts.json`・`brief.md`・`*_market-report.html` はスクリプトが作る。手で直さない
