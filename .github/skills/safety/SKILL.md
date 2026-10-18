---
name: safety
description: 安全性分析スキル。企業分析フレームワーク.md の STEP 2-3（安全性: 自己資本比率・D/E レシオ・流動比率の直近値を目安と同業平均で判定し、ネットキャッシュがプラスなら実質無借金、5年の推移で悪化傾向を、有利子負債が増えた年の CF で借入の目的（成長投資/赤字補填）を見て 安全性 良好/普通/懸念（材料不足なら判定保留） を判定）を、collect-company-info が集めた財務時系列・有報・競合の材料から行い、companies/{ticker}_{name}/analysis/safety/ に Markdown と JSON で保存する。数値の計算と判定はすべて Python スクリプトが行い、LLM は数値の背景と引き継ぎだけを書く。結果は180日有効で、期間内は再分析しない（新しい決算期・財務時系列・競合の収集があれば再分析）。材料が足りなければ collect-company-info を先に実行する。STEP 1・収益性は前提にせず、収益性の結果と地合いの金利の行は brief に引用するだけ。財務の安全性・自己資本比率・有利子負債・無借金・財務体力を分析したいときに使う。
---

`.ai/skills/safety.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・安全性の状態・分析日・結論・収益性の結論・最終収集日）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `collect` のときは、`.github/skills/collect-company-info/SKILL.md` と `.ai/skills/collect-company-info.md` を読み、collect-company-info を**逐次モード**で実行する（`mode=update`、`needs_full_collect` なら `mode=full`）。担当は `missing_inputs` の `agent` だけ、範囲はその `items` に絞る。完了報告まで終えてから、このスキルの手順 1 に戻る
- 収集の作業で読んだ raw・抜粋・検索結果は、安全性の執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 執筆の編集は欄ごとに1回

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `companies/{ticker}_{name}/analysis/safety/{日付}_safety.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_brief.md`・`{日付}_safety.json` はスクリプトが作る。手で直さない
