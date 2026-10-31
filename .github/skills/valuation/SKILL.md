---
name: valuation
description: バリュエーション分析スキル。企業分析フレームワーク.md の STEP 3（今の株価は妥当か: 3-1 PER（特別損益が純利益の10%以上なら調整EPS、予想PER で判定し会社計画を割り引くなら実績PER も、赤字・営業赤字・50%以上の減益は評価対象外）、3-2 PBR（適正PBR = 予想ROE × 過去5年の平均PER、1倍割れ・ROE 8%未満で改善策が無ければバリュートラップとして妥当）、3-3 PEG（成長率の3ケース、5%未満・利益の半減は評価対象外、悲観ケースの安全域）、3-4 EV/EBITDA（EV と EBITDA を算出し過去レンジも算出、PER との食い違いの理由）を、過去5年レンジでの位置と同業中央値との差の共通ルールで 割安/妥当/割高/評価対象外 に判定し、点数の平均と STEP 2・SWOT による最終確認で STEP 3 割安/妥当/割高（材料不足なら判定保留））を、collect-company-info が集めた株価データ・競合・財務時系列の材料と成長性分析の結果から行い、companies/{ticker}_{name}/analysis/valuation/ に Markdown と JSON で保存する。数値の計算と判定はすべて Python スクリプトが行い、LLM は背景と、バリュートラップのときの改善策の有無だけを書く。株価は日々動くため結果は7日有効で、株価の基準日が7日より古ければ collect-company-info で株価を取り直す。成長性分析が未実施なら先に growth を実行する（成長性の結論では止めない）。PER・PBR・PEG・EV/EBITDA・割安か割高か・STEP 3 のバリュエーションを分析したいときに使う。
---

`.ai/skills/valuation.md` を読み、その手順に厳密に従って実行する。

引数（company・redo）はユーザーの依頼文から読み取る。企業が指定されていなければ手順 0 で選んでもらう。

## GitHub Copilot での実行方法

- コマンドはターミナルで実行する。Python は `.venv\Scripts\python.exe`（Windows）/ `.venv/bin/python`（macOS・Linux）
- 手順 0（企業の選択）は、`list` の結果を番号付きの一覧（番号・企業名・ディレクトリ・バリュエーションの状態・分析日・結論・成長性の結論・最終収集日）にしてチャットに出し、ユーザーが番号か企業名で答えるのを待つ。答えが来るまで先に進まない。企業が1社だけなら一覧を出さずにその企業で進む
- 手順 1 で `growth` のときは、`.github/skills/growth/SKILL.md` と `.ai/skills/growth.md` を読み、growth を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、`.github/skills/collect-company-info/SKILL.md` と `.ai/skills/collect-company-info.md` を読み、collect-company-info を**逐次モード**で実行する（`mode=update`、`needs_full_collect` なら `mode=full`）。担当は `missing_inputs` の `agent` だけ、範囲はその `items` に絞る。完了報告まで終えてから、このスキルの手順 1 に戻る
- 収集・成長性分析の作業で読んだ raw・抜粋・検索結果は、バリュエーションの執筆に持ち込まない（執筆は brief.md だけを根拠にする）
- 執筆の編集は欄ごとに1回

## 書き込みガード（Copilot では手動で確認する）

Claude Code では hook が自動でブロックするが、Copilot には hook が無い。**ファイルを編集する前に毎回**次を実行し、`BLOCKED` と出たら編集しない。

```
python -I tools/guard/write_guard.py --check <編集するファイルのパス>
```

- このスキルで編集してよいのは `companies/{ticker}_{name}/analysis/valuation/{日付}_valuation.md` の `<!-- FILL:... -->` の部分（と build が指摘した箇所）だけ。ファイルの新規作成・全体の書き換えはしない
- `{日付}_brief.md`・`{日付}_valuation.json` はスクリプトが作る。手で直さない
