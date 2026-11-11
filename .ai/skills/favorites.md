# お気に入り企業の管理スキル（favorites）

企業分析レポート（`/company-report`）を GitHub Actions で定期実行する企業（お気に入り）を、管理台帳 `companies/favorites.json` に登録・削除する。

- **A グループ**: 平日（月〜金）0:30 JST に実行
- **B グループ**: 平日（月〜金）6:00 JST に実行
- 各グループ **5社まで**。1社はどちらか一方のグループにだけ入る
- **企業分析レポートを一度も作っていない企業（`reports/{日付}_company-report.json` が無い企業）は登録できない**。先に `/company-report` で作る

**台帳の読み書き・上限や条件の確認はすべてスクリプト（`tools/report/favorites.py`）が行う。** 台帳は手で編集しない（`tools/guard/write_guard.py` がブロックし、台帳の `digest` が手修正を検出してワークフローを止める）。
LLM が受け持つのは、依頼から操作（追加・削除・付け替え・一覧）と企業・グループを読み取り、スクリプトを実行して結果を報告することだけ。

---

## 引数

| 引数 | 内容 | 省略時 |
|---|---|---|
| 操作 | `add`（追加）・`remove`（削除）・`move`（グループの付け替え）・`list`（一覧） | `list` |
| `company` | 銘柄コード（`3798`）・企業ディレクトリ名（`3798_uls-group`）・社名の一部。複数可 | — |
| `group` | `A` または `B`（add・move のとき） | 手順 2 で確かめる |

---

## 実行手順

Python は `.venv` のものを使う（Windows: `.venv\Scripts\python.exe`、macOS/Linux: `.venv/bin/python`）。以下 `$PY` と書く。
各コマンドの標準出力は1行の JSON（失敗時は `ok: false` と `error`）。

### 1. 現状の確認

```
$PY -I tools/report/favorites.py list
```

`groups` の各行（`company`・`added`・`report_date`）と `issues`（台帳の問題）を見る。`issues` があるときは手順 3 の表に従う。

### 2. 操作の決定

- 操作が `list` だけなら手順 4 へ
- add・move でグループの指定が無いときは、グループの空き（5 − 登録数）を示してユーザーに確かめる（推測で決めない）
- 企業が複数のときは1社ずつ手順 3 を実行する

### 3. 実行

```
$PY -I tools/report/favorites.py add    --company {company} --group {A|B}
$PY -I tools/report/favorites.py remove --company {company}
$PY -I tools/report/favorites.py move   --company {company} --group {A|B}
```

| 結果 | すること |
|---|---|
| `ok: true` | 次の企業へ（全部終わったら手順 4） |
| `candidates` あり | 複数の企業が当たった。候補からユーザーに選んでもらい、もう一度実行する |
| 「一度も作っていない」 | 登録できない。`/company-report {company}` でレポートを作ってから登録するよう伝える（このスキルからは実行しない） |
| 「上限」 | そのグループは5社。もう一方のグループへの登録か、どの企業を remove / move するかをユーザーに確かめる |
| 「既にグループ X にある」 | add ではなく move の依頼かをユーザーに確かめる |
| `issues` に「手で書き換えられている」 | 台帳が手で編集された。add・move は拒否される。`list` の内容をユーザーに見せ、正しい状態をユーザーに確かめたうえで、remove（手修正でも通る）と add で正しい状態に戻す。台帳を手で直さない |
| `issues` に「companies/ に無い」「build されていない」 | その企業を remove する（ディレクトリが無い企業も、ディレクトリ名そのままで remove できる） |

### 4. 完了報告（ユーザー向け）

最後の `list` の JSON だけを使い、次の形式で短く報告する。

```
## お気に入り企業
- 今回の操作: {追加・削除・付け替えした企業とグループ。無ければ「なし（一覧のみ）」}
- A グループ（平日 0:30 JST・{n}/5 社）: {company（最新レポート report_date）を「、」で。無ければ「なし」}
- B グループ（平日 6:00 JST・{n}/5 社）: {同上}
- 登録できなかった企業: {company と理由。無ければ「なし」}
- 台帳の問題: {issues。無ければ「なし」}
```

台帳の変更は git にコミットされるまでワークフローに反映されない（ワークフローは main の台帳を読む）。コミットはユーザーの指示があるときだけ行う。

---

## してはいけないこと

- `companies/favorites.json` を Write・Edit で直接書かない（hook がブロックする）。ブロックされたら回避策を探さず、スクリプトで操作する
- グループ・企業を推測で決めない
- このスキルから `/company-report` や分析スキルを実行しない
- 台帳の上限（各グループ5社）や登録条件（レポートが build 済み）を回避しない
