---
name: valuation
description: バリュエーション分析スキル。企業分析フレームワーク.md の STEP 3（今の株価は妥当か: 3-1 PER（特別損益が純利益の10%以上なら調整EPS、予想PER で判定し会社計画を割り引くなら実績PER も、赤字・営業赤字・50%以上の減益は評価対象外）、3-2 PBR（適正PBR = 予想ROE × 過去5年の平均PER、1倍割れ・ROE 8%未満で改善策が無ければバリュートラップとして妥当）、3-3 PEG（成長率の3ケース、5%未満・利益の半減は評価対象外、悲観ケースの安全域）、3-4 EV/EBITDA（EV と EBITDA を算出し過去レンジも算出、PER との食い違いの理由）を、過去5年レンジでの位置と同業中央値との差の共通ルールで 割安/妥当/割高/評価対象外 に判定し、点数の平均と STEP 2・SWOT による最終確認で STEP 3 割安/妥当/割高（材料不足なら判定保留））を、collect-company-info が集めた株価データ・競合・財務時系列の材料と成長性分析の結果から行い、companies/{ticker}_{name}/analysis/valuation/ に Markdown と JSON で保存する。数値の計算と判定はすべて Python スクリプトが行い、LLM は背景と、バリュートラップのときの改善策の有無だけを書く。株価は日々動くため結果は7日有効で、株価の基準日が7日より古ければ collect-company-info で株価を取り直す。成長性分析が未実施なら先に growth を実行する（成長性の結論では止めない）。PER・PBR・PEG・EV/EBITDA・割安か割高か・STEP 3 のバリュエーションを分析したいときに使う。
argument-hint: "[{銘柄コード|企業ディレクトリ名|社名の一部}] [redo]  ※省略時は companies/ から選択"
---

`.ai/skills/valuation.md` を読み、その手順に厳密に従って実行する。

引数: $ARGUMENTS

## Claude Code での実行方法

- 手順 0（企業の選択）は AskUserQuestion で選択肢を出す。選択肢は最大4つなので、企業が5社以上あるときは `valuation` が `fresh` 以外の企業を優先し、その中で分析日が古い順（未分析が先）に4社を出す（ほかの企業は「その他」で入力してもらう）。各選択肢の説明にバリュエーションの状態・分析日・結論・成長性の結論・最終収集日を書く。企業が1社だけなら AskUserQuestion を出さずにその企業で進む（AskUserQuestion は選択肢が2つ以上要る）
- 手順 1 で `growth` のときは、Skill ツールで `growth` を起動する（引数は `{ticker}`）。その手順書を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- 手順 1 で `collect` のときは、Skill ツールで `collect-company-info` を起動する。引数は `{ticker} mode=update 担当={missing_inputs の agent をカンマ区切り} 項目={items}`（`needs_full_collect` なら `mode=full`）。その手順書（並列モード）を最後の完了報告まで実行してから、このスキルの手順 1 に戻る
- スクリプトは1コマンドずつ実行する（check の `next` を見てから prepare）。Windows で Bash ツールが動かないときは PowerShell ツールで `.venv\Scripts\python.exe -I tools/analysis/valuation.py check --company {company}` のように実行する
- collect-company-info を起動するときに、raw の書き方（範囲外の章の扱い・再掲）を引数やプロンプトで指定しない
- 執筆（手順 3）はサブエージェントに任せず、自分で brief.md を読んで valuation.md を Edit する。Edit は欄ごとに1回
- 書き込みは `tools/guard/write_guard.py`（PreToolUse hook）が監視する。ブロックされたら回避策を探さず、指摘に従う
