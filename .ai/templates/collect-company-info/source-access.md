# 取得経路の対応表（collect-company-info 参照資料）

情報源ごとに「どの手段で取れるか」と URL パターンをまとめる。新しい知見を得たら追記する。
最終確認: 2026-10-11（3798 ULSグループでの実行時）

## 手段の凡例

| 手段 | 説明 |
|---|---|
| WebFetch | AI の WebFetch ツール（HTML を要約して返す。JS 描画は読めない） |
| fetch.py | `tools/collect/fetch.py` でダウンロードし sources/ に保存（PDF/HTML 原本が手元に残る） |
| EDINET API | `tools/collect/edinet.py`（要 `EDINET_API_KEY`） |
| ブラウザ | Playwright MCP（拡張が入っている環境のみ。preflight 時に1回試す） |

## 情報源ごとの可否

| 情報源 | WebFetch | fetch.py | 備考・URL パターン |
|---|---|---|---|
| 企業サイトの静的ページ（会社概要・事業紹介） | ○ | ○ | まずここから |
| 企業サイトのIR一覧（E-IR / IRPocket 等のウィジェット） | ×（JS描画） | ×（中身は空） | **解析しない**。下の代替経路へ。判別: HTML に `eir-parts.net` や `data-area-name` がある |
| E-IR 文書 | — | ○ | `https://ssl4.eir-parts.net/doc/{code}/yuho_pdf/{EDINET書類番号}/00.pdf`（有報・半期・四半期）、`.../ir_material_for_fiscal_ym1/{id}/00.pdf`（説明資料）、`.../announcement1/{id}/00.pdf`（株主総会） |
| 東証 適時開示（TDnet 原本） | ×（403） | ○ | PDF: `https://www2.jpx.co.jp/disc/{code}0/{開示番号}.pdf`。短信 iXBRL: `https://www2.jpx.co.jp/disc/{code}0/{...}-ixbrl.htm`。開示番号は IRBANK の適時開示一覧で調べる |
| 株探 TDnet ミラー | — | ○ | `https://tdnet-pdf.kabutan.jp/{YYYYMMDD}/{開示番号}.pdf`（JPX で 404 のときの代替） |
| IRBANK | ○ | ○ | 適時開示一覧 `https://irbank.net/{EDINETコード}/tdnet`（開示番号と見出しが取れる）、決算まとめ `https://irbank.net/{code}/results`、銘柄ページ `https://irbank.net/{code}`（株価・PER/PBR・年次レンジ）。**二次情報** |
| EDINET DB | ○ | — | IR資料一覧 `https://edinetdb.jp/company/{EDINETコード}/ir-docs/`（eir-parts の PDF URL が載っている）。**二次情報** |
| 株探 | ×（403、`kabutan.jp`） | — | `https://s.kabutan.jp/stocks/{code}/news/` は WebFetch 可（直近20件）。決算記事 `s.kabutan.jp/stocks/{code}/news/k{YYYYMMDD}{nnnn}/` に期初予想が載る。**二次情報** |
| EDINET API v2 | — | — | `edinet.py list/fetch`。書類一覧は日付単位なので `--fy-end-month` で提出月だけ走査 |
| かぶよほ（アナリスト予想） | 未確認 | — | 検索結果の要約でのみ取得実績あり |

## IR一覧の代替経路（公式サイトが JS 描画の場合）

1. IRBANK 適時開示一覧（開示番号・日付・見出し）→ 東証 PDF を fetch.py
2. EDINET DB の IR資料一覧（説明資料・有報の eir-parts URL）→ fetch.py
3. 株探ニュース一覧（s. サブドメイン、直近分）
4. Web 検索（`{社名} 決算説明会資料 {年}` など）

## 既知の環境の問題

| 事象 | 対処 |
|---|---|
| Read ツールで PDF が読めない（poppler 無し） | `pdf_text.py` でテキスト化し、`find_pages.py` で必要ページだけ読む |
| curl が SSL 検証エラー（Windows） | `fetch.py`（certifi を使用）を使う |
| Bash ツールで `$変数` が展開されない | シェル変数を使わず、スクリプトに引数で渡す |

## 米国株（2026-10-14 CBRS Cerebras での実行時）

| 情報源 | WebFetch | fetch.py | 備考・URL パターン |
|---|---|---|---|
| SEC EDGAR（www.sec.gov / data.sec.gov） | ○ | ○（要 `SEC_USER_AGENT`） | SEC は連絡先入りの User-Agent（`名前 メールアドレス`）を要求する。`.env` の `SEC_USER_AGENT` が無いと fetch.py・edgar.py は失敗する（preflight の「SEC EDGAR（米国株）」で確認）。一覧と年次財務は `edgar.py list / facts`。提出書類一覧は `https://data.sec.gov/submissions/CIK{10桁}.json`、XBRL の年次値は `https://data.sec.gov/api/xbrl/companyfacts/CIK{10桁}.json`、本文は `https://www.sec.gov/Archives/edgar/data/{CIK}/{accession(ハイフンなし)}/{file}.htm` |
| 企業 IR サイト（gcs-web / Q4 系、例: investors.cerebras.ai） | ×（403、Cloudflare） | ×（403） | 決算発表は 8-K の Ex.99.1（EDGAR）で代替。説明会資料・質疑応答は取得不可 |
| 企業サイトのプレスリリース（例: www.cerebras.ai/press-release/...） | ○ | ○ | `sitemap.xml` に一部の URL が載る（lastmod は公表日ではない） |
| Yahoo Finance チャート API | — | — | `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1y&interval=1d` で日次 OHLC。**二次** |

- IPO 直後の会社は 10-K が無い。年次は 424B4（最終目論見書）と S-1 で代替し、四半期は 10-Q を使う
- `xbrl_financials.py` / `tdnet_summary.py` は日本株専用のため、米国株は `data/financials.csv` を作れない（raw に手で転記する）
