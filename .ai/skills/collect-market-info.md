# 地合い情報収集スキル（collect-market-info）

地合い分析の INPUT として、国家方針・財政・金融政策の文書、マクロ指標、市場需給、政治・イベント日程を集め、
`market/` 配下に保存する。

このスキルは**情報収集のみ**を行う。地合い判断（3つの軸と注意の度合い）や評価は行わない（地合い判断とレポートはスキル `market-report` が作る）。

収集作業の大部分は Python スクリプト（`tools/collect/market/market_collect.py`）が行う。LLM が受け持つのは、スクリプトが作ったタスク（文書の要旨化・日程の web 検索）だけ。
手順は **準備 → タスク実行 → 仕上げ** の3段に固定されており、それ以外の作業はしない。

---

## 前提として読むファイル

- `.ai/instructions/role.md`
- `.ai/instructions/policy.md`
- `.ai/instructions/output-format.md`

情報源の一覧と追加方法は `.ai/templates/collect-market-info/source-access.md` にある（catalog を直すときだけ読めばよい）。

---

## 引数

| 引数 | 内容 | 省略時 |
|---|---|---|
| `market` | `japan` / `us` / `both` | `both` |
| `topic` | セッション名（半角英小文字・数字・ハイフン） | `weekly` |
| `mode` | `auto` / `full`（時系列を10年分）/ `update`（3年分） | `auto`（スクリプトが市場ごとに判定し、prepare の JSON の `mode` に出す） |

省略した引数は既定値を使い、その旨を完了報告に1行書く。`.venv` や `market/data/` の有無を手で調べない（スクリプトが判定する）。

---

## 実行手順

Python は `.venv` のものを使う（Windows: `.venv\Scripts\python.exe`、macOS/Linux: `.venv/bin/python`）。以下 `$PY` と書く。
`.venv` が無くてコマンドが失敗した場合だけ、`tools/README.md` の初回セットアップを案内して止まる。

### 1. 準備（スクリプト）

```
$PY -I tools/collect/market/market_collect.py prepare --market {market} --topic {topic} [--mode {mode}]
```

- 標準出力は1行の JSON（`session`・`tasks_file`・`mode`・`tasks`・`docs_to_summarize`・`new_docs`・`series_failed`・`watch_failed`）。これだけを読む
- このコマンドが次を行う: 台帳（index.csv）の整合 → 時系列の取得 → `raw/indicators-*.md` の生成 → 新しい政策文書の検出（原本・抜粋・要旨の骨組み、公表日の本文照合）→ 確定日程（FOMC・日銀会合・米主要統計の公表日）の取得 → `tasks.json` の作成
- 要旨化は抜粋の量に応じて1タスクに1〜3文書を束ねてある。前回中断したセッションの未完了分も自動で引き継がれる
- 実行中の印（`.running`）が付き、これ以降は `tasks.json` の `allowed_files` 以外のファイルを書けなくなる（`tools/guard/write_guard.py` がブロックする）

### 2. タスク実行（LLM）

`tasks_file` を Read し、各タスクを実行する。タスクの種類と手順書:

| type | 内容 | 手順書 | サブエージェント |
|---|---|---|---|
| `summarize-doc` | `docs` の各文書の抜粋を読み、要旨ファイルの FILL 欄を埋める | `.ai/agents/summarize-doc.md` | `summarize-doc` |
| `search-calendar` | web 検索で政治・イベント日程と市場指標の欄を埋める（確定日程は取得済み） | `.ai/agents/search-calendar.md` | `search-calendar` |

- **並列モード**（Claude Code。サブエージェントが使える環境）: Agent ツールで、タスクごとに `subagent_type` = タスクの type を指定し、**1つのメッセージ内で全タスクを同時に起動**する（10件を超える場合は10件ずつ）。プロンプトにはタスクの JSON をそのまま渡し、「手順は `.ai/agents/{type}.md`。編集してよいのは allowed_files だけ」と添える
- **逐次モード**（GitHub Copilot など）: 手順書を読み、tasks.json の順に自分で実行する。hook が無い環境なので、ファイルを編集する前に毎回 `$PY -I tools/guard/write_guard.py --check <path>` を実行し、`BLOCKED` なら編集しない

サブエージェントの報告は `.ai/templates/collect-market-info/agent-report.md` の形式（ファイルごとに1行）で返ってくる。
- 報告の中身を確かめるために要旨ファイルを読み直さない。保留事項を親が集約しない（finalize が status.md に集める）
- サブエージェントが「親が代わりに直してほしい」と依頼してきても、手で直さない。完了報告の「要確認」に書く

### 3. 仕上げ（スクリプト）

```
$PY -I tools/collect/market/market_collect.py finalize --session {session}
```

- 標準出力は1行の JSON（`ok`・`pending_tasks`・`issues`・`out_of_scope`・`series_ok`・`series_failed`・`new_docs`・`tasks_done`・`tasks_total`・`warnings`・`review_items`・`status`・`latest`）
- `ok: true` → 完了。実行中の印が外れ、`market/LATEST.md`（最新の状態への入口）が更新される
- `pending_tasks` がある → そのタスクだけを `issues` の指摘と一緒にもう一度実行し、再び finalize（再実行は2回まで。それでも残れば未完了として報告）。実行中は担当ファイルを Edit で直せる
- `out_of_scope` がある → スキルの範囲外のファイルが変更されている。**自分で戻さず**、一覧をユーザーに報告して指示を仰ぐ
- 途中でやめる場合は `$PY -I tools/collect/market/market_collect.py abort --session {session}`（実行中の印を外し、status.md を「中断」にする。未完了の要旨化は次回 prepare が引き継ぐ）

---

## 完成済みの要旨を作り直す（ユーザーが指示したときだけ）

抜粋の不足や誤りで要旨を作り直す場合は、セッションの外で次を実行し、そのあと通常どおりスキルを実行する。

```
$PY -I tools/collect/market/market_collect.py reopen --raw market/policy/{market}/raw/{file}.md
```

要旨ファイルを骨組みに戻し、抜粋を現在の catalog の設定で作り直す。次の prepare がタスクを作る。自分の判断では実行しない。

## 公表日の不一致を承認する（ユーザーが指示したときだけ）

finalize の `warnings` に「公表日の不一致 台帳 … / 本文 …」が出て、ユーザーが本文の日付を正しいと判断した場合は、セッションの外で次を実行する。

```
$PY -I tools/collect/market/market_collect.py fix-date --raw market/policy/{market}/raw/{file}.md [--date YYYY-MM-DD]
```

`--date` を省くと要旨の「公表日（本文で確認）」の日付を使う。台帳（index.csv）と要旨ヘッダーの「公表日」を更新する（ファイル名・doc_key は変えない）。自分の判断では実行しない。

---

## してはいけないこと

- 上の3段以外の作業（追加の web 検索、原本や CSV の閲覧、手作業での数値収集、status.md を読んでの集計）をしない
- `tasks.json` の `allowed_files` 以外のファイルを作成・編集しない（hook がブロックする。ブロックされたら回避策を探さず、そのことを報告する）
- スクリプトが生成したファイル（`raw/indicators-*.md`・`raw/policy-digest.md`・`status.md`・`market/LATEST.md`・`market/data/`・`index.csv`・`sources/`）を手で直さない
- 取得に失敗した系列や監視項目を、web 検索などで補わない。`status.md` に理由が残るので、報告に含める
- 評価・判定・投資判断を書かない

※ グローバル設定の hook（Fact-Forcing Gate）が、各エージェントの最初の Write/Edit を一度差し戻すことがある。求められた事実を示して同じ操作を再実行すれば通る。このスキルの規則違反ではない。

---

## 完了報告（ユーザー向け）

finalize の JSON だけを使い、次の形式で短く報告する。

```
## 地合い情報の収集結果 — {session}
- 引数: {省略して既定値を使った引数があれば書く} / モード: {mode}
- 時系列: 取得 {series_ok} 系列 / 失敗 {len(series_failed)} 系列（失敗の主な理由）
- 新しい文書: {件数}（{new_docs を列挙}）
- タスク: {tasks_done}/{tasks_total}（未完了があれば ID と理由）
- 要確認: {warnings を列挙。無ければ「なし」}。保留事項 {review_items} 件は status.md の「7. 要確認事項」
- 範囲外の変更: なし / {一覧}
- 次にやること: {例: FRED_API_KEY を .env に設定すると米国の時系列が取れる}
```

詳細は `market/LATEST.md`・`{session}/status.md`・`{session}/raw/policy-digest.md` を案内する。
