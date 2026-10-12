# 地合いレポート作成スキル（market-report）

collect-market-info が集めた材料（時系列・指標表・日程・政策文書の要旨）を統合し、日米の市場動向と
短期・中期・長期の展望をまとめた**週次レポート**を作る。成果物は次の2つ。

- `market/report/{週}_market-report.html` — プレゼンテーション形式の単一 HTML（13 スライド。外部ファイル不要でオフラインでも開ける）
- `market/report/{週}_outlook.md` — 地合い判断（強気/中立/慎重/弱気）と展望。企業分析はこのファイルを参照する

`{週}` は出力週の**月曜日**（YYYY-MM-DD）。同じ週に再実行すると同じファイル名になる。

数値・チャート・日程はスクリプト（`tools/report/market_report.py`）が収集データから機械的に作る。
LLM が受け持つのは outlook.md の FILL 欄（判断と文章）だけ。手順は **鮮度確認 → 準備 → 執筆 → ビルド** の4段に固定されている。

---

## 前提として読むファイル

- `.ai/instructions/role.md`
- `.ai/instructions/policy.md`
- `.ai/instructions/output-format.md`

---

## 引数

| 引数 | 内容 | 省略時 |
|---|---|---|
| `week` | 出力週の任意の日（YYYY-MM-DD）。その週の月曜日がファイル名になる | 今日 |
| `redo` | 完成済みの outlook.md を作り直す（ユーザーが指示したときだけ） | なし |

省略した引数は既定値を使い、その旨を完了報告に1行書く。

---

## 実行手順

Python は `.venv` のものを使う（Windows: `.venv\Scripts\python.exe`、macOS/Linux: `.venv/bin/python`）。以下 `$PY` と書く。

### 1. 鮮度確認（スクリプト）

```
$PY -I tools/report/market_report.py check [--week {week}]
```

標準出力は1行の JSON（`week`・`latest_session`・`fresh`・`running`・`outlook`・`html_exists`・`reason`）。

| 状態 | すること |
|---|---|
| `running` が空でない | 収集が実行中。**止めて**ユーザーに報告する（収集を横から始めない） |
| `fresh: false` | 材料が出力週より古い。collect-market-info を `market=both topic=weekly` で実行する（起動方法はエントリーポイントの指示に従う）。finalize が `ok: true` で終わったら check をもう一度実行する。`ok: true` にならなければ止めて、収集の完了報告と一緒にユーザーに報告する |
| `outlook: "done"` | この週のレポートは作成済み。ユーザーが作り直しを指示していなければ、既存の HTML の場所を伝えて終わる。指示があれば手順 2 で `--redo` を付ける |
| `fresh: true` | 手順 2 へ |

### 2. 準備（スクリプト）

```
$PY -I tools/report/market_report.py prepare --week {week} [--redo]
```

- `facts.json`（数値・チャート用系列・日程・文書一覧）・`brief.md`（執筆の材料）・`outlook.md`（FILL 欄つきの骨組み）を `market/report/` に作る
- 作成途中の outlook.md（FILL が残っている）は上書きせずに残す（`outlook_kept: true`）。続きから書く
- 標準出力の `kpis_missing`（取れなかった主要指標）・`series_failed` は完了報告に使う

### 3. 執筆（LLM）

`brief.md` を読み、`outlook.md` の `<!-- FILL:... -->` を Edit で置き換える。

- 読むのは brief.md と outlook.md だけ。CSV・原本・要旨ファイル・status.md を個別に開かない（必要な要点は brief.md に集約済み）
- 書き方の規則は outlook.md 冒頭の `>` 行と各節の説明に従う。要点:
  - 判断は `強気` / `中立` / `慎重` / `弱気` の1語。2段階で迷ったら低い方（不利な方）を採る（policy.md 行動指針6）
  - 3章は「見たもの → 情報源 → 結論」。見たものには brief.md の数値と時点を、情報源には brief.md の節またはファイル名を書く
  - 4章の展望は 短期（今後1か月。次回の FOMC・日銀会合まで）・中期（6か月程度）・長期（1〜3年）。基本シナリオは「何が続く／変わる前提か」を書き、株価・為替の水準は予想しない
  - 前回の判断（brief.md 10.）から変えた場合は、1章の要約に変えた理由を書く
  - 取れていない指標（—）を推測で埋めない。判断に効く欠損は 7章に書く
- 見出し・表の列・ヘッダー・スクリプト記入済みの欄（6章の日付・イベントなど）は変えない。ファイルを丸ごと書き直さない（Write は hook がブロックする）

### 4. ビルド（スクリプト）

```
$PY -I tools/report/market_report.py build --week {week}
```

- `ok: true` → `html` に出力先、`judgments` に日米の判断が入る。完了。`warnings`（作成途中の outlook.md が古い収集から作られている など）があれば完了報告に書く。自分では `--redo` しない
- `ok: false` → `issues` の指摘箇所だけを Edit で直し、もう一度 build（2回まで。それでも残れば未完了として、指摘をそのまま報告する）

---

## してはいけないこと

- 4段以外の作業（追加の web 検索、CSV や原本の閲覧、数値の手計算・手入力）をしない。材料が足りなければ 7章に書く
- スクリプトが作るファイル（`facts.json`・`brief.md`・`*_market-report.html`）を手で直さない（hook がブロックする）
- 過去の週の完成済み outlook.md を変更しない。`--redo`・`--allow-stale` は自分の判断で使わない（ユーザーの指示があるときだけ）
- 投資の勧誘・推奨、株価・為替の水準予想、「おそらく」「〜と思われる」を書かない（build が検出する）

※ グローバル設定の hook（Fact-Forcing Gate）が最初の Edit を一度差し戻すことがある。求められた事実を示して同じ操作を再実行すれば通る。

---

## 完了報告（ユーザー向け）

build の JSON と prepare の JSON だけを使い、次の形式で短く報告する。

```
## 地合いレポート — {week} 週
- レポート: {html}（判断の根拠: {outlook}）
- 地合い判断: 日本 {judgments.japan}（前回 {previous.japan または「初回」}）/ 米国 {judgments.us}（前回 …）
- 材料: 収集セッション {session}（今回 collect-market-info を実行した / しなかった）
- 欠損: 主要指標 {kpis_missing を列挙。無ければ「なし」}、取得失敗の系列 {series_failed} 件
- 次にやること: {例: FRED_API_KEY を設定すると株価指数が取れる}
```
