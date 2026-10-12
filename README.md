# corporate-analysis

日本株・米国株の投資判断を支援するための、企業分析・地合い分析リポジトリです。

AI エージェント（Claude Code / GitHub Copilot）が「スキル」として情報収集と分析を行い、データの取得・検証・ファイル生成は Python スクリプトが担います。収集した原本・生データ・分析結果はすべてこのリポジトリ内に日付付きで保存されるため、根拠をあとから辿れます。

> AI は分析と材料の整理を支援するだけで、投資の最終判断・推奨・株価予測はしません。投資判断は自己責任で行ってください（[.ai/instructions/role.md](.ai/instructions/role.md)）。

## 分析の流れ

```
地合い:  collect-market-info ──▶ market-report ──▶ market/report/{週}_outlook.md
                                                          │ 参照
企業:    collect-company-info ──▶ five-forces ──▶ three-c ──▶ （以降 STEP 1〜3 の分析）
```

企業分析は次の 3STEP で進めます。STEP 1 か 2 で C 判定になったら、その時点で終了します。

| STEP | 観点 | 問い | 分析手法 |
|---|---|---|---|
| 1 | 事業・競争環境 | 良いビジネスか | ファイブフォース → 3C → モート → SWOT |
| 2 | 財務 | 数字が裏付けているか | 収益性 / 成長性 / 安全性 / キャッシュフロー |
| 3 | バリュエーション | 今の株価は妥当か | PER / PBR / PEG / EV/EBITDA |

## セットアップ（環境ごとに1回）

Python 3 が必要です。

```powershell
pwsh tools/setup.ps1      # Windows
sh tools/setup.sh         # macOS / Linux / Git Bash
```

- リポジトリ直下に `.venv` を作り、`tools/requirements.txt` をインストールします
- `.env` が無ければ `.env.example` からコピーします。必要に応じて次のキーを記入してください（どちらも無料）
  - `EDINET_API_KEY`: 有価証券報告書の XBRL 取得
  - `FRED_API_KEY`: 米国のマクロ指標と株価指数（日経平均・S&P500・NASDAQ）
- 最後に `preflight.py` が実行され、使える取得経路が表示されます

設定はすべてこのリポジトリ内（`.venv`、`.env`、`.claude/settings.json`）で完結します。詳細は [tools/README.md](tools/README.md) を参照してください。

## 使い方

Claude Code でこのリポジトリを開き、スラッシュコマンドでスキルを実行します。引数は自然文でも構いません。GitHub Copilot では `.github/skills/` から同じスキルを使えます。

| スキル | 用途 | 実行例 |
|---|---|---|
| `collect-company-info` | 企業情報の収集（IR資料・有報/10-K・財務時系列・業界/競合・株価指標）。2回目以降は `mode=update` で差分だけを更新 | `/collect-company-info https://www.ulsgroup.co.jp/ japan` |
| `collect-market-info` | 地合い情報の収集（国家方針・財政・金融政策の文書、マクロ指標・需給の時系列、政治・イベント日程） | `/collect-market-info both topic=weekly` |
| `market-report` | 週次の地合いレポート（プレゼン形式の HTML と、地合い判断 `outlook.md`）。今週の収集が無ければ先に収集を行う | `/market-report` |
| `five-forces` | ファイブフォース分析（業界の魅力度 高/中/低）。結果は365日有効。材料が足りなければ先に収集を行う | `/five-forces 3798` |
| `three-c` | 3C分析（顧客・競合・自社から、勝てる理由 明確/あいまい/なし（材料不足なら判定保留））。結果は180日有効。ファイブフォースが未実施なら先に実行し、材料が足りなければ先に収集を行う | `/three-c 3798` |

- `collect-company-info` に渡す情報: 銘柄コード・企業名（英語）・ホームページURL・市場（japan / us）。URL だけでも構いません
- `five-forces`・`three-c` は銘柄コード・企業ディレクトリ名・社名の一部のどれでも指定できます。省略すると一覧から選べます

### おすすめの手順

1. `/collect-market-info` → `/market-report` で今週の地合いを確認する（週1回）
2. 分析したい企業を `/collect-company-info` で収集する
3. `/five-forces` で STEP 1 の業界分析を始め、`/three-c` で会社の立ち位置（勝てる理由）を分析する（`/three-c` だけでも、ファイブフォースが未実施なら先に実行される）
4. 結果は `companies/{ticker}_{name}/analysis/` に、地合いは `market/report/` に出力されます

## ディレクトリ構成

```
.
├── CLAUDE.md                  # Claude Code への共通指示
├── .ai/                       # AI 共通の定義（実体）
│   ├── instructions/          #   役割・行動指針・出力形式
│   ├── skills/                #   スキルの手順書
│   ├── agents/                #   サブエージェント（並列収集・要旨化など）
│   └── templates/             #   出力テンプレート
├── .claude/                   # Claude Code のエントリーポイント（skills / agents）と設定・hook
├── .github/                   # GitHub Copilot のエントリーポイント（copilot-instructions.md・skills）
├── companies/                 # 企業ごとの収集データと分析結果（{ticker}_{name}/）
├── market/                    # 地合い分析（文書ライブラリ・時系列・セッション・週次レポート）
└── tools/                     # Python スクリプト（collect / report / analysis / guard）
```

詳しい構造は次を参照してください。

- 出力形式・命名規則・全体の構造: [.ai/instructions/output-format.md](.ai/instructions/output-format.md)
- 企業ディレクトリ: [companies/README.md](companies/README.md)
- 地合い分析: [market/README.md](market/README.md)
- スクリプト: [tools/README.md](tools/README.md)

## 運用ルール

- `raw/`（収集した生データ）は変更禁止です。誤りに気づいた場合も上書きせず、再収集します
- `data/`・`sources/`・`index.csv`・`tasks.json`・`status.md` などスクリプトが生成するファイルは、手で編集しません
- これらのルールは書き込みガード（[tools/guard/write_guard.py](tools/guard/write_guard.py)、Claude Code の PreToolUse hook）が強制します
- 原本（`sources/`）と `.env`・`.venv` は git 管理外です。原本は `sources/manifest.csv` の URL から別の環境でも再取得できます
- AI の行動指針と禁止事項: [.ai/instructions/policy.md](.ai/instructions/policy.md)

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest tools/collect/tests tools/report/tests tools/analysis/tests -q
```
