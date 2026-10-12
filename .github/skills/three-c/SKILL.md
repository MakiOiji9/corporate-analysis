---
name: three-c
description: 3C分析スキル。企業分析フレームワーク.md の STEP 1-2（顧客・競合・自社を分析し、顧客の KBF・市場の成長性・競合との比較 優位/同等/劣位・KBF ごとの自社と競合の比較から、勝てる理由 明確/あいまい/なし（材料不足なら判定保留） を判定）を、collect-company-info・collect-market-info・market-report が集めた材料とファイブフォースの結果から行い、companies/{ticker}_{name}/analysis/three-c/ に Markdown と JSON で保存する。結果は180日有効で、期間内は再分析しない（新しい有報・事業概要・業界・競合の収集や新しいファイブフォース分析があれば再分析）。ファイブフォースが未実施なら先に five-forces、材料が足りなければ収集スキルを実行する。会社の立ち位置・勝てる理由・3C を分析したいときに使う。
---

`.ai/skills/three-c.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・3Cの状態・分析日・結論・ファイブフォースの状態・最終収集日）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `five_forces` のときは、`.github/skills/five-forces/SKILL.md` と `.ai/skills/five-forces.md` を読み、five-forces を同じ企業で最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、`.github/skills/collect-company-info/SKILL.md` と `.ai/skills/collect-company-info.md` を読み、collect-company-info を**逐次モード**で実行する（`mode=update`、`needs_full_collect` なら `mode=full`）。担当は `missing_inputs` の `agent` だけ、範囲はその `items` に絞る。完了報告まで終えてから、このスキルの手順 1 に戻る
- five-forces・収集の作業で読んだ raw・抜粋・検索結果は、3C の執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 執筆の編集は章・表ごとに1回

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `companies/{ticker}_{name}/analysis/three-c/{日付}_three-c.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_brief.md`・`{日付}_three-c.json` はスクリプトが作る。手で直さない
