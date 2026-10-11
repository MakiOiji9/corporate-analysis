# 地合い情報の情報源と catalog の書き方

収集対象は `tools/collect/market/catalog/{japan,us}.json` で定義する（スクリプトはこの JSON だけを見る）。
情報源を足す・直すときは catalog を編集し、`market_collect.py check-watch` / `search` で確認してから使う。

## 層と取得方法

| 層 | 日本 | 米国 | 取得 | 保存先 |
|---|---|---|---|---|
| A 国家方針 | 所信表明・施政方針演説（官邸）、骨太の方針（内閣府）、新しい資本主義 実行計画（内閣官房）、エネルギー基本計画（資源エネルギー庁） | 大統領令・布告の一覧（White House）、一般教書演説 | 監視ページ → 原本・抜粋 → LLM が要旨化（一覧は要旨化しない） | `market/policy/{market}/` |
| B 財政・税制 | 総合経済対策、税制改正の大綱、予算のポイント（財務省）、中長期の経済財政に関する試算 | CBO Budget and Economic Outlook | 同上 | 同上 |
| C 金融政策 | 日銀 決定会合の公表文・展望レポート（基本的見解）・主な意見・議事要旨 | FOMC 声明・議事要旨、ベージュブック | 同上 | 同上 |
| D マクロ指標 | 金利（日銀・財務省）、ドル円、CPI・雇用・賃金・GDP・鉱工業生産・景気動向指数・機械受注（e-Stat 統計ダッシュボード）、短観（日銀）、月例経済報告（要旨化） | FRED（金利・物価・雇用・GDP・小売・生産・住宅・消費者信頼感） | API → `market/data/{market}_series.csv` → 表 | セッションの `raw/indicators-*.md` |
| E 需給・政治 | 投資部門別売買（JPX 週次 xlsx）／ 日程・支持率・予想PER は web 検索 | VIX（FRED）、CFTC 建玉 ／ 日程・支持率・予想PER・AAII は web 検索 | スクリプト + search-calendar タスク | `raw/indicators-*.md`、`raw/calendar-*.md` |

## API キー

| キー | 用途 | 未設定のとき |
|---|---|---|
| `FRED_API_KEY` | 米国の時系列（FRED） | 米国の FRED 系列は「FRED_API_KEY 未設定」として `status.md` に残り、表は `—` |

日本の時系列（日銀 API・e-Stat 統計ダッシュボード・財務省 CSV・JPX）と CFTC はキー不要。

## catalog: series（時系列）

```json
{"id": "JP_UNEMP", "name": "完全失業率（季節調整値）", "group": "雇用・賃金",
 "provider": "dashboard", "params": {"indicator": "0301010000020020010", "cycle": "1", "seasonal": "2"},
 "frequency": "monthly", "transform": "level", "unit": "%", "decimals": 1,
 "source": "総務省 労働力調査（統計ダッシュボード）", "source_url": "https://dashboard.e-stat.go.jp/"}
```

| provider | params | 系列コードの探し方 |
|---|---|---|
| `boj` | `db`, `code` | `market_collect.py search boj --db FM01 --word 無担保コール`（名前は全角混じり。例「Ｏ／Ｎ」） |
| `dashboard` | `indicator`, `cycle`（1=月 2=四半期 3=年）, `seasonal`（1=原数値 2=季節調整値。省略可） | `market_collect.py search dashboard --word 有効求人倍率` |
| `mof_jgb` | `tenor`（`2年` `10年` など CSV の列名） | — |
| `fred` | `id`（FRED の series ID） | https://fred.stlouisfed.org/ で検索 |
| `cftc` | `contract`（CFTC contract market code。E-mini S&P500 = 13874A） | — |
| `jpx_flows` | `investor`（xlsx の投資部門名に含まれる語。例 `海外投資家`） | — |

- `frequency`: `daily` / `weekly` / `monthly` / `quarterly`（`daily` の「前回」は約1か月前）
- `transform`: `level`（そのまま）/ `yoy_pct`（前年同期比を計算）/ `diff`（前回差を計算）
- 日付の正規化: 月次は月初、四半期は期首月の1日（例: 2026年7-9月期 = 2026-07-01）

## catalog: watch（文書の監視）

```json
{"key": "boj-statement", "layer": "C", "kind": "summarize", "type": "html_links",
 "title": "日本銀行 金融政策決定会合 公表文", "url": "https://www.boj.or.jp/{boj_state_page}",
 "link_pattern": "mpr_\\d{4}/k\\d{6}a\\.pdf$", "date_pattern": "k(?P<y>\\d{2})(?P<m>\\d{2})(?P<d>\\d{2})a\\.pdf",
 "use_entry_title": true, "max_new": 1}
```

| キー | 意味 |
|---|---|
| `type` | `html_links`（ページ内リンク）/ `rss` |
| `kind` | `summarize`（原本を保存して要旨化タスクを作る）/ `list`（新着の一覧だけを残す） |
| `link_pattern` / `title_pattern` | リンク URL / リンク文字に対する正規表現 |
| `follow` | 候補ページを開き、その中の本文 PDF などに差し替える（見つからない候補は飛ばす） |
| `date_pattern` | URL から日付を読む正規表現（名前付きグループ `y` `m` `d`） |
| `use_entry_title` | リンク文字が「PDF」だけのページで、`title`＋日付を表題にする |
| `max_new` / `max_chars` | 1回に取り込む件数 / 要旨化に渡す抜粋の上限文字数 |
| `vars`（catalog 直下） | URL の `{名前}` を、別ページから正規表現で読んだ値で置き換える（内閣番号・年ごとのページなど） |

新着の判定: 一覧を新しい順に見て、`index.csv` に登録済みの URL に当たったところで止める（古い版を後から拾わない）。全候補に日付があれば日付の新しい順に並べ替えてから判定する。

## 自動化していない情報源（必要なら catalog に追加）

- GX2040ビジョン・経済安全保障・防衛力整備計画・規制改革実施計画（不定期。掲載ページが案件ごとに違う）
- 財務省 対外及び対内証券売買契約等の状況（週次）、信用残・裁定残（JPX）
- 米国 大統領予算教書（OMB）、財務省 Quarterly Refunding、ISM（FRED に無い）
- 日銀の RSS は直近の掲載分しか載らないため、主な意見・議事要旨は1か月以上あけると取りこぼすことがある（各年のページを watch に足すか、月1回以上実行する）
