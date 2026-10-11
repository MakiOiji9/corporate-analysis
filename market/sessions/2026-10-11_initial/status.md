# 収集ステータス — market/sessions/2026-10-11_initial

**更新日時**: 2026-10-11T22:36
**段階**: prepare 完了（タスク実行待ち）

> market_collect.py が prepare / finalize のたびに上書きする。手で編集しない。

## 1. 概要

| 項目 | 値 |
|---|---|
| 市場 | 日本・米国 |
| モード | full |
| 新規文書 | 6 |
| タスク | 18 件（未完了 18 件） |

## 2. 時系列

| 市場 | 系列 | 最終時点 | 状態 |
|---|---|---|---|
| japan | 無担保コールO/N物レート（平均） | 2026-10-07 | OK |
| japan | 国債利回り 2年 | 2026-10-08 | OK |
| japan | 国債利回り 10年 | 2026-10-08 | OK |
| japan | 国債利回り 30年 | 2026-10-08 | OK |
| japan | ドル円（東京市場 9時時点） | 2026-10-07 | OK |
| japan | 消費者物価指数 総合（2025年基準） | 2026-08-01 | OK |
| japan | 消費者物価指数 生鮮食品を除く総合（2025年基準） | 2026-08-01 | OK |
| japan | 消費者物価指数 生鮮食品及びエネルギーを除く総合（2025年基準） | 2026-08-01 | OK |
| japan | 完全失業率（季節調整値） | 2026-08-01 | OK |
| japan | 有効求人倍率（季節調整値） | 2026-08-01 | OK |
| japan | 実質賃金指数 現金給与総額 | 2026-08-01 | OK |
| japan | 実質GDP（前期比年率） | 2026-04-01 | OK |
| japan | 鉱工業生産指数（2020年=100、季節調整値） | 2026-08-01 | OK |
| japan | 景気動向指数 CI 一致指数（2020年=100） | 2026-08-01 | OK |
| japan | 景気動向指数 CI 先行指数（2020年=100） | 2026-08-01 | OK |
| japan | 機械受注（船舶・電力を除く民需） | 2026-07-01 | OK |
| japan | 日銀短観 業況判断DI 大企業製造業（実績） | 2026-07-01 | OK |
| japan | 日銀短観 業況判断DI 大企業製造業（先行き） | 2026-10-01 | OK |
| japan | 日銀短観 業況判断DI 大企業非製造業（実績） | 2026-07-01 | OK |
| japan | 投資部門別売買 海外投資家 差引（東名二市場） | 2026-10-02 | OK |
| japan | 投資部門別売買 個人 差引（東名二市場） | 2026-10-02 | OK |
| japan | 投資部門別売買 信託銀行 差引（東名二市場） | 2026-10-02 | OK |
| japan | 投資部門別売買 事業法人 差引（東名二市場） | 2026-10-02 | OK |
| us | FF金利 誘導目標上限 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 米国債利回り 2年 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 米国債利回り 10年 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 長短金利差（10年−2年） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | ハイイールド社債スプレッド（ICE BofA） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 消費者物価指数 総合 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 消費者物価指数 コア（食品・エネルギー除く） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | PCE価格指数 コア | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 失業率 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 非農業部門雇用者数（前月差） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 新規失業保険申請件数 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 求人件数（JOLTS） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 実質GDP（前期比年率） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 小売売上高 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 鉱工業生産指数 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | 住宅着工件数（年率） | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | ミシガン大学 消費者信頼感指数 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | VIX 指数 | — | 失敗: ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| us | CFTC 建玉 E-mini S&P500 非商業部門ネット | 2026-10-06 | OK |

## 3. 文書監視

| 市場 | 監視項目 | 結果 |
|---|---|---|
| japan | pm-speech | 候補 1 件 / 新規 0 件 |
| japan | honebuto | 候補 14 件 / 新規 0 件 |
| japan | new-capitalism | 候補 3 件 / 新規 0 件 |
| japan | energy-plan | 候補 1 件 / 新規 0 件 |
| japan | economic-measures | 候補 4 件 / 新規 0 件 |
| japan | tax-reform | 候補 2 件 / 新規 0 件 |
| japan | budget | 候補 29 件 / 新規 0 件 |
| japan | fiscal-projection | 候補 26 件 / 新規 0 件 |
| japan | monthly-report | 候補 33 件 / 新規 0 件 |
| japan | boj-statement | 候補 5 件 / 新規 0 件 |
| japan | boj-outlook | 候補 50 件 / 新規 0 件 |
| japan | boj-opinions | 候補 1 件 / 新規 0 件 |
| japan | boj-minutes | 候補 1 件 / 新規 0 件 |
| us | presidential-actions | 候補 30 件 / 新規 0 件 |
| us | sotu | 候補 0 件 / 新規 0 件 |
| us | cbo-outlook | 候補 0 件 / 新規 0 件 |
| us | fomc-statement | 候補 4 件 / 新規 0 件 |
| us | fomc-minutes | 候補 4 件 / 新規 0 件 |
| us | beige-book | 候補 6 件 / 新規 0 件 |

## 4. タスク（LLM 担当）

| ID | 種類 | 出力ファイル | 状態 |
|---|---|---|---|
| T01 | summarize-doc | market/policy/japan/raw/2026-10-11_pm-speech-2026-10-05.md | 未完了 |
| T02 | summarize-doc | market/policy/japan/raw/2026-10-11_new-capitalism-2026-10-11.md | 未完了 |
| T03 | summarize-doc | market/policy/japan/raw/2026-10-11_energy-plan-2025-02-18.md | 未完了 |
| T04 | summarize-doc | market/policy/japan/raw/2026-10-11_boj-statement-2026-09-18.md | 未完了 |
| T05 | summarize-doc | market/policy/japan/raw/2026-10-11_boj-outlook-2026-07-01.md | 未完了 |
| T06 | summarize-doc | market/policy/japan/raw/2026-10-11_boj-opinions-2026-10-01.md | 未完了 |
| T07 | summarize-doc | market/policy/japan/raw/2026-10-11_boj-minutes-2026-09-28.md | 未完了 |
| T08 | summarize-doc | market/policy/japan/raw/2026-10-11_honebuto-2026-07-21.md | 未完了 |
| T09 | summarize-doc | market/policy/japan/raw/2026-10-11_economic-measures-2025-11-21.md | 未完了 |
| T10 | summarize-doc | market/policy/japan/raw/2026-10-11_tax-reform-2025-12-26.md | 未完了 |
| T11 | summarize-doc | market/policy/japan/raw/2026-10-11_budget-2025-08-08.md | 未完了 |
| T12 | summarize-doc | market/policy/japan/raw/2026-10-11_fiscal-projection-2026-01-22.md | 未完了 |
| T13 | summarize-doc | market/policy/japan/raw/2026-10-11_monthly-report-2026-09-29.md | 未完了 |
| T14 | search-calendar | market/sessions/2026-10-11_initial/raw/calendar-japan.md | 未完了 |
| T15 | summarize-doc | market/policy/us/raw/2026-10-11_fomc-statement-2026-09-16.md | 未完了 |
| T16 | summarize-doc | market/policy/us/raw/2026-10-11_fomc-minutes-2026-10-07.md | 未完了 |
| T17 | summarize-doc | market/policy/us/raw/2026-10-11_beige-book-2026-08-01.md | 未完了 |
| T18 | search-calendar | market/sessions/2026-10-11_initial/raw/calendar-us.md | 未完了 |

## 5. 検証結果

- 問題なし

## 6. スキルの範囲外の変更

- なし
