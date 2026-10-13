---
name: swot
description: SWOT分析スキル。企業分析フレームワーク.md の STEP 1-4（1-1〜1-3 の結果と中期経営計画・事業等のリスク・業界・地合いの事実を 強み/弱み/機会/脅威 に振り分け、影響度 大/中/小 を評価し、最大の強みで最大の脅威に対抗できるかを SWOT Yes/条件付き/No（材料不足なら判定保留） で判定）を、collect-company-info・collect-market-info・market-report が集めた材料とファイブフォース・3C・モートの結果から行い、companies/{ticker}_{name}/analysis/swot/ に Markdown と JSON で保存する。結果は180日有効で、期間内は再分析しない（新しい有報・中期経営計画・事業概要・業界の収集や新しい上流の分析があれば再分析）。モートが未実施なら先に moat、地合いが古ければ market-report、材料が足りなければ collect-company-info を実行する。SWOT・STEP 1 の総括・最大の強みと脅威を分析したいときに使う。
---

`.ai/skills/swot.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・SWOT の状態・分析日・結論・モートの状態・最終収集日）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `moat` のときは、`.github/skills/moat/SKILL.md` と `.ai/skills/moat.md` を読み、moat を同じ企業で最後の完了報告まで実行してから、このスキルの手順 1 に戻る（moat の中で 3C・ファイブフォース・収集が必要なら、moat の手順どおりに行う）
- 手順 1 で `market_report` のときは、`.github/skills/market-report/SKILL.md` と `.ai/skills/market-report.md` を読み、market-report を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、`.github/skills/collect-company-info/SKILL.md` と `.ai/skills/collect-company-info.md` を読み、collect-company-info を**逐次モード**で実行する（`mode=update`、`needs_full_collect` なら `mode=full`）。担当は `missing_inputs` の `agent` だけ、範囲はその `items` に絞る。完了報告まで終えてから、このスキルの手順 1 に戻る
- moat・market-report・収集の作業で読んだ raw・抜粋・検索結果は、SWOT の執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 執筆の編集は章・表ごとに1回

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `companies/{ticker}_{name}/analysis/swot/{日付}_swot.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_brief.md`・`{日付}_swot.json` はスクリプトが作る。手で直さない
