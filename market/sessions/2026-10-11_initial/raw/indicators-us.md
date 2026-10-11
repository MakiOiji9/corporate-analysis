# マクロ指標・市場需給 — 米国

**収集日**: 2026-10-11
**情報源**:
- https://fred.stlouisfed.org/ — 確度: 一次
- https://publicreporting.cftc.gov/ — 確度: 一次
**原本**: なし（API・公表 CSV/Excel から取得。時系列は `market/data/us_series.csv`）

> market_collect.py prepare が生成する。手で編集しない（再取得は prepare を再実行）。
> 値は公表値の転記と、その単純計算（前年比・前回差）だけ。評価・判定は含めない。
> 「前回」は直前の公表値（日次系列は約1か月前）、「1年前」は1年前の同じ時点。取得できなかった系列は「—」とし、理由を2章に書く。

## 1. 指標一覧

| 区分 | 指標 | 時点 | 値 | 前回（時点） | 1年前（時点） | 単位 | 出典 |
|---|---|---|---|---|---|---|---|
| 金利・為替 | FF金利 誘導目標上限 | — | — | — | — | % | FRB（FRED） |
| 金利・為替 | 米国債利回り 2年 | — | — | — | — | % | 米財務省（FRED） |
| 金利・為替 | 米国債利回り 10年 | — | — | — | — | % | 米財務省（FRED） |
| 金利・為替 | 長短金利差（10年−2年） | — | — | — | — | %ポイント | FRB セントルイス（FRED） |
| 金利・為替 | ハイイールド社債スプレッド（ICE BofA） | — | — | — | — | %ポイント | ICE BofA（FRED） |
| 物価 | 消費者物価指数 総合 | — | — | — | — | 前年同月比 % | 米労働省 BLS（FRED） |
| 物価 | 消費者物価指数 コア（食品・エネルギー除く） | — | — | — | — | 前年同月比 % | 米労働省 BLS（FRED） |
| 物価 | PCE価格指数 コア | — | — | — | — | 前年同月比 % | 米商務省 BEA（FRED） |
| 雇用 | 失業率 | — | — | — | — | % | 米労働省 BLS（FRED） |
| 雇用 | 非農業部門雇用者数（前月差） | — | — | — | — | 千人 | 米労働省 BLS（FRED） |
| 雇用 | 新規失業保険申請件数 | — | — | — | — | 件 | 米労働省（FRED） |
| 雇用 | 求人件数（JOLTS） | — | — | — | — | 千件 | 米労働省 BLS（FRED） |
| 景気 | 実質GDP（前期比年率） | — | — | — | — | 前期比年率 % | 米商務省 BEA（FRED） |
| 景気 | 小売売上高 | — | — | — | — | 前年同月比 % | 米商務省（FRED） |
| 景気 | 鉱工業生産指数 | — | — | — | — | 前年同月比 % | FRB（FRED） |
| 景気 | 住宅着工件数（年率） | — | — | — | — | 千戸 | 米商務省（FRED） |
| 景気 | ミシガン大学 消費者信頼感指数 | — | — | — | — | 指数 | ミシガン大学（FRED） |
| 需給 | VIX 指数 | — | — | — | — | ポイント | Cboe（FRED） |
| 需給 | CFTC 建玉 E-mini S&P500 非商業部門ネット | 2026-10-06 | -154,070 | -142,499（2026-09-29） | -136,689（2025-09-30） | 枚（プラスはネットロング） | CFTC Commitments of Traders |

## 2. 取得できなかった系列

| 指標 | 理由 |
|---|---|
| FF金利 誘導目標上限 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 米国債利回り 2年 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 米国債利回り 10年 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 長短金利差（10年−2年） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| ハイイールド社債スプレッド（ICE BofA） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 消費者物価指数 総合 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 消費者物価指数 コア（食品・エネルギー除く） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| PCE価格指数 コア | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 失業率 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 非農業部門雇用者数（前月差） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 新規失業保険申請件数 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 求人件数（JOLTS） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 実質GDP（前期比年率） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 小売売上高 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 鉱工業生産指数 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| 住宅着工件数（年率） | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| ミシガン大学 消費者信頼感指数 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
| VIX 指数 | ProviderError: FRED_API_KEY 未設定（.env に設定すると取得できる） |
