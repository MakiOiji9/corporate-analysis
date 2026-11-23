---
name: investment
description: 投資の質の分析スキル。会社が何に投資したか（有報の設備投資等の概要・設備の新設計画・研究開発活動・企業結合・株式の保有状況を過去最大10期、data/investments.json から）を年ごとの表にし、どこで変化したか（投資の急増・急減、セグメント配分、研究開発、M&A、攻めと守りの局面、新しい投資テーマ）を示し、① 投資効率（増分 ROIC。以前の成長性の手順5から移した）・② 中期経営計画と設備計画との整合・③ 世界の潮流（業界の構造変化・政策）との整合・④ 競合比較（売上に対する成長投資の同業中央値との比較）・⑤ 失敗の履歴（減損・のれん）・⑥ 資金と規律（建設仮勘定・投資不足・資金源・テーマの継続性・政策保有株）から 投資の質 良好/普通/懸念（材料不足なら判定保留） を判定し、companies/{ticker}_{name}/analysis/investment/ に Markdown と JSON で保存する。数値・変化点・判定は Python スクリプトが出し、LLM は何に投資したか・投資テーマとその潮流との照合・変化点の背景・中計と設備計画の照合だけを書く。結果は365日有効（新しい期の有報・中期経営計画・業界データ、またはファイブフォース・3C の結論が変わったら再分析）。材料が足りなければ collect-company-info を先に実行する。何に投資したか・設備投資・M&A・投資の質を分析したいときに使う。
---

`.ai/skills/investment.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・投資の質の状態・分析日・結論・data/investments.json の有無）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `collect` のときは、`.github/skills/collect-company-info/SKILL.md` と `.ai/skills/collect-company-info.md` を読み、collect-company-info を**逐次モード**で実行する（`mode=update`、`needs_full_collect` なら `mode=full`）。担当は `missing_inputs` の `agent` だけ、範囲はその `items` に絞る。完了報告まで終えてから、このスキルの手順 1 に戻る
- 収集の作業で読んだ raw・抜粋・検索結果は、執筆に持ち込まない（執筆は brief.md だけを根拠にする）

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `companies/{ticker}_{name}/analysis/investment/{日付}_investment.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_brief.md`・`{日付}_investment.json` はスクリプトが作る。手で直さない
