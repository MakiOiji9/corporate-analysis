# プレスリリース・重要ニュース（2026-10-15〜2026-11-11） — Cerebras Systems Inc.（CBRS）

**収集日**: 2026-11-11
**情報源**:
- 企業サイト プレスリリース一覧（https://www.cerebras.ai/company/press-release、WebFetch）と各 /press-release/ ページ — 確度: 一次（原本は未保存。WebFetch 要約）
- SEC EDGAR 8-K 一覧（`edgar.py list --ticker CBRS --forms 8-K`）: 2026-08-12 の後に新しい 8-K・10-Q の提出なし — 確度: 一次
- 報道（CNBC、FinanceFeeds、TIKR、FourWeekMBA、AD-HOC-NEWS、TipRanks ほか。WebSearch / WebFetch の要約）— 確度: 二次／検索要約（該当行に明記）
- IR サイト https://investors.cerebras.ai は前回 HTTP 403 のため再取得せず。企業サイトの一覧に載らない開示の漏れは否定できない
**原本**: 今回は sources/ に保存していない（プレスリリースは WebFetch 要約のみ。8-K の新規提出なし）

> 確度の定義: 一次＝会社・取引所・官公庁の原本 / 二次＝転載・集計 / 検索要約＝Web検索結果の要約のみで原本未確認
> 期間: 前回ファイル（2025-10-14〜2026-10-14）の1章は 2026-08-12 以降を切れ目なく含むため、今回の 2026-10-15〜2026-11-11 と合わせて直近3か月（2026-08-11〜）を満たす。前回ファイルに無かった 2026-09-30〜2026-10-02 の株価に関わる報道は、時系列の連続のため冒頭に補う（前回の行は再掲しない）。
> 2026-10-15 以降の会社の開示は、決算発表日の告知・Oracle・Bilt の3件のみ（企業サイトの一覧）。8-K の提出はなし。

## 1. 適時開示・プレスリリース
| 日付 | 見出し | 要旨 | URL | 確度 |
|---|---|---|---|---|
| 2026-09-30（補足） | 株主ロックアップの第1段階解除 | 取締役・役員・一般従業員・非従業員株主の最大1,940万株（発行済みの約8%）が解除。2026-08-19 以降は2週間ごとに最大1,460万株が解除されている。CEO Feldman と CTO Sean Lie は 2026-08-20〜09-25 に計 $240 million 超を取引計画で売却（CNBC） | https://www.cnbc.com/2026/10/02/cerebras-stock-hits-post-ipo-low-on-nvidia-pressure-lockup-expiration.html | 二次（CNBC） |
| 2026-09-30〜10-02（補足） | SemiAnalysis: OpenAI は GPT-6.1 Sol の「Ultrafast」モードを Nvidia GPU で動かす（X への投稿） | 会社・OpenAI・Nvidia による確認なし。10-02 に Sam Altman が X で「Cerebras は近しいパートナーで、速度のフロンティアで深く関与している」と投稿し、時間外で約3%上昇。株価は週間で約20%下落し 10-02 終値 $166.43（上場後最安、IPO 価格 $185 を下回る。時価総額 約 $39 billion） | https://www.cnbc.com/2026/10/02/cerebras-stock-hits-post-ipo-low-on-nvidia-pressure-lockup-expiration.html | 二次（CNBC。SemiAnalysis・Altman の投稿は孫引き） |
| 2026-10-16 | 52週安値を更新（TipRanks 記事の日付） | OpenAI が高速サービスで Nvidia を選ぶ可能性の報道を受けた懸念が続く。年初来 -54.3%、時価総額 約 $31.7 billion | https://www.tipranks.com/news/catalyst/lockup-expiry-and-openai-jitters-hammer-cerebras-stock | 二次 |
| 2026-10-20 | Cerebras Systems Announces Date of Third-Quarter 2026 Financial Results | 2026Q3 決算を 2026-11-12（木）の米市場の引け後に発表。電話会見は同日 2 p.m. PT（5 p.m. ET）、investors.cerebras.ai で配信 | https://www.cerebras.ai/press-release/cerebras-systems-announces-date-of-third-quarter-2026-financial-results-3384934 | 一次（原本なし。WebFetch 要約） |
| 2026-10-27 | Cerebras and Oracle Team Up to Bring Cerebras AI Inference to Oracle Cloud Infrastructure | Oracle Cloud Infrastructure（OCI）で Cerebras の高速推論を提供する計画。提供開始は2027暦年。金額・性能数値・顧客数の記載なし。将来の製品方針であり提供を約束するものではないと注記。この日の株価は約 +10%、終値 $119.31（FourWeekMBA の記載） | https://www.cerebras.ai/press-release/cerebras-and-oracle-team-up-to-bring-cerebras-ai-inference-to-oracle-cloud-inf-3389429 | 一次（原本なし。WebFetch 要約）／株価は二次 |
| 2026-10-27〜10-28 | 役員の Form 144 / Form 4（Sean Lie） | 10-27 の Form 144 で 60,000株（約 $6.5 million）の売却を届出、翌日の Form 4 で売却を確認。ほかに COO Dhiraj Mallick が 09-29 に 396,000株（約 $80.8 million、10b5-1 計画。Form 4 は 09-30 提出）を売却（FinanceFeeds の記載。SEC の原本は未確認） | https://financefeeds.com/cbrs-stock-cerebras-lock-up-expires-ahead-of-nov-12-q3-results/ | 二次（FinanceFeeds。Form 4 原本は未取得） |
| 2026-10-28 | Culper Research が空売りレポートを公表（X への投稿） | ウェハ型チップの実使用寿命は約1.5〜2.5年（別の報道は1.4〜2.3年）で、会社の使用可能年数 3〜5 年の仮定は不当と主張。IPO 書類のドラフトでは 2025-12 まで 1.5〜3 年だったのが 2026-04 の S-1 で 3〜5 年に変わったと指摘し、2.25年なら 2026年上期の粗利率は 29.9% でなく 24.0% と試算。Culper は空売り保有を開示。主張は意見であり、一部の根拠は匿名の元従業員・顧客。株価は 10-28 に約 -10%（報道により -4%〜-11%でばらつき） | https://www.tikr.com/blog/cerebras-sinks-10-as-short-seller-culper-claims-its-wafers-break-down-after-just-2-years | 二次（TIKR、Mitrade、Letsdatascience。Culper 報告書の原本は未確認） |
| 2026-11-02 | UBS が目標株価を $330 から $250 に引き下げ（Buy 維持） | AD-HOC-NEWS の記載（11-09 付の記事）。同記事は Wedbush $290→$190（Outperform 維持）、Rosenblatt $300→$170（Buy 維持。評価方法を 2028 暦年売上の 14 倍から 2028 年度の 1 株当たり売上の 8 倍に変更）も報じるが、日付は不明。格下げ（ダウングレード）の明確な報道は確認できず | https://www.ad-hoc-news.de/boerse/news/unternehmensnachrichten/cerebras-faces-a-double-test-insider-lockup-expiry-meets-a-round-of-target-cuts/70482626 | 検索要約（ad-hoc-news。各社の原本レポートは未取得） |
| 2026-11-05 | Andrew Feldman が Culper の主張に反論（ブログ「What It Took to Build Wafer-Scale, and Why It Lasts」、X で共有） | CS-3 導入後に撤去されたウェハは 0.5% 未満。使用可能年数は研究用機器の時期の 1〜3 年から、自社クラウドの本番運用に移った後の 3〜5 年に見直した（大手クラウドは AI 機器を 5〜6 年とする例が多いとも主張）。見積もりは KPMG の年次監査の対象。Culper の挙げた接続材（PariPoser）の使用は否定。熱による故障は 33 年相当などは熱だけのモデル推計で実測の寿命ではない。11-05 の株価終値 $81.71（10-27 の $119.31 から -31.5%、前日比 -11.0%。同日の AI 株安の影響もあり反論だけの効果とは言えない）。日中安値 $77.84（11-05） | https://www.cerebras.ai/blog/what-it-took-to-build-wafer-scale-and-why-it-lasts | 一次（会社ブログ。本文は未取得）／株価は二次（FourWeekMBA、FinanceFeeds） |
| 2026-11-06 | 終値 $89.68（FinanceFeeds の記載） | — | https://financefeeds.com/cbrs-stock-cerebras-lock-up-expires-ahead-of-nov-12-q3-results/ | 二次 |
| 2026-11-09 | 主力ロックアップの終了（目論見書日付 2026-05-13 から 180 日、午前 6:00 ET） | ロックアップ対象は Class A 普通株と関連転換証券の約 71.4%。会社推計では早期解除条項により全期間で最大約 1.711 億株が解除対象（取締役・役員保有の最大 1,500 万株を含む累計の数値で、11-09 当日の解除量ではない）。Rule 144 の制限（関係者）が残るため直ちに市場に出るとは限らない。MarketBeat・Fox11 は 11-10 と報じ、FinanceFeeds は 11-09 とする。10-Q の「決算発表後 2 営業日目」の代替条件なら 11-16 になるが 180 日条項が先に到来。11-09 日中 $93.79 | https://financefeeds.com/cbrs-stock-cerebras-lock-up-expires-ahead-of-nov-12-q3-results/ ／ https://www.marketbeat.com/instant-alerts/lockup-cerebras-systems-incs-lock-up-period-will-end-on-november-10th-nasdaq-cbrs-2026-11-03/ | 二次（日付は報道間で不一致。10-Q 2026-06期の記載が一次） |
| 2026-11-10 | Bilt Selects Cerebras to Deliver Faster AI Experiences to More than Eight Million Members | Bilt（会員 800万人超、加盟店 5万超）が新 AI プラットフォーム Bilt Neighborhood OS と Bilt Concierge の推論に Cerebras を採用。金額・開始時期の記載なし。11-10 終値 $93.66 | https://www.cerebras.ai/press-release/bilt-selects-cerebras-to-deliver-faster-ai-experiences-to-more-than-eight-mill-3399287 | 一次（原本なし。WebFetch 要約）／終値は親の指定値 |

2026Q3 決算は 2026-11-12 発表予定（収集日の翌日）で、収集日時点では未発表。会社ガイダンス（コア）は売上 $214〜216 million、粗利率 38〜40%、営業利益率 (25)〜(23)%（2026-08-12 発表）。市場予想は売上 約 $215.8〜219 million、1株損益 (0.13)〜(0.14) ドル（Earnings Whispers、Chartmill の検索要約）。
