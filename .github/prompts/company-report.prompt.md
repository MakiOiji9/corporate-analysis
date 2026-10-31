---
mode: agent
description: 企業分析レポート。STEP 1〜3 の分析スキルを依存の順に実行し（鮮度が新しい分析はスキップ）、短期・中期・長期の判定と株価の過去レンジを載せた日付付きの単一 HTML を companies/{ticker}_{name}/reports/ に作る。
---

`.ai/prompts/company-report.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・新しくない分析・最新のレポートの日付と状態）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `next` がスキル名のときは、`.github/skills/{スキル名}/SKILL.md` と `.ai/skills/{スキル名}.md` を読み、そのスキルを最後の完了報告まで実行してから、この手順の手順 1 に戻る（collect-company-info を呼ぶスキルは逐次モードで実行する）
- 同じスキルを1回の実行で2回実行しない。2回目に `next` に出たら止まって報告する
- 分析スキルの作業で読んだ raw・抜粋・検索結果は、レポートの執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 執筆の編集は欄ごとに1回

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このコマンドで編集してよいのは `companies/{ticker}_{name}/reports/{日付}_company-report.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_company-report.html`・`.json`・`_facts.json`・`_brief.md` と `data/prices.csv` はスクリプトが作る。手で直さない
