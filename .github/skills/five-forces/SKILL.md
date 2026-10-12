---
name: five-forces
description: ファイブフォース分析スキル。企業分析フレームワーク.md の STEP 1-1（新規参入・代替品・買い手・売り手・業界内競争の5要因を 強/中/弱 で評価し、業界の魅力度 高/中/低 を判定）を、collect-company-info・collect-market-info・market-report が集めた材料から行い、companies/{ticker}_{name}/analysis/five-forces/ に Markdown と JSON で保存する。結果は365日有効で、期間内は再分析しない（新しい有報・業界・競合の収集があれば再分析）。材料が足りなければ収集スキルを先に実行する。業界の魅力度・ファイブフォースを分析したいとき、企業分析の STEP 1 を始めるときに使う。
---

`.ai/skills/five-forces.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・状態・分析日・魅力度・最終収集日）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `collect` のときは、`.github/skills/collect-company-info/SKILL.md` と `.ai/skills/collect-company-info.md` を読み、collect-company-info を**逐次モード**で実行する（`mode=update`、`needs_full_collect` なら `mode=full`）。担当は `missing_inputs` の `agent` だけ、範囲はその `items` に絞る。完了報告まで終えてから、このスキルの手順 1 に戻る
- 収集の作業で読んだ raw・抜粋・検索結果は、ファイブフォースの執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 執筆の編集は要因ごとに1回（その要因の表の FILL 行をまとめて置き換える）

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `companies/{ticker}_{name}/analysis/five-forces/{日付}_five-forces.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_brief.md`・`{日付}_five-forces.json` はスクリプトが作る。手で直さない
