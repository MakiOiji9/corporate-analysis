"""Refresh only the share prices of the valuation inputs (自社と競合の確定終値を同じ基準日でそろえる), without an agent.

Usage:
  refresh_valuation.py --company 3798 [--date YYYY-MM-DD]

valuation is valid for 7 days, so a report re-run usually needs only new prices. This script takes the share count,
EPS and BPS already in the raw files (株価データ 1章・2章, 競合 6章) and the peers' codes (競合 1.2 の「採用」の行),
fetches the newest common closing price of the company and every peer (Yahoo Finance chart API, the same endpoint
as stock_prices.py; 二次), and writes two dated raw files of the changed chapters only:
  raw/ir/{date}_valuation-data.md   1章 (株価・時価総額。株式数などの行は前回のまま) and 3章 (PER・PBR)
  raw/market/{date}_competitors.md  6章 (株価・時価総額・PER・PBR。EV/EBITDA は分析スクリプトが 11章・12章から計算)
then the 株価 row of status.md and one line of overview.md's 情報収集履歴. Nothing is written when a peer has no
code or no price for the base date, when today's files already exist, or when a needed number is missing: the
output names what is missing and the fallback (collect-company-info, collect-peers-valuation 「株価のみ」).
stdout is one JSON line. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path[:0] = [str(HERE), str(HERE / "market"), str(TOOLS / "analysis"), str(TOOLS / "report")]

import mdparse as M  # noqa: E402
import stock_prices as SP  # noqa: E402
import va_inputs as VI  # noqa: E402
import va_paths as VP  # noqa: E402
import va_series as VS  # noqa: E402
from common import REPO_ROOT, atomic_write_text, http_get, utf8_stdout  # noqa: E402
from ff_inputs import raw_files  # noqa: E402
from series import ProviderError  # noqa: E402
from tc_metrics import same_company  # noqa: E402

LOOKBACK_DAYS = 14  # enough trading days to find a common close after holidays
FALLBACK = "collect-company-info（mode=update、担当 collect-peers-valuation、項目「株価のみ」）"
PEER_HEADER = ["会社", "株価", "時価総額", "PER（実績）", "PER（予想）", "PBR", "EV/EBITDA", "EPS（実績）", "EPS（予想）", "BPS"]
EV_NOTE = "—（11章・12章から分析スクリプトが計算）"
CODE = re.compile(r"^\s*([0-9A-Z][0-9A-Z.\-]{0,9})\s*(?:・|$)")
NAME_CODE = re.compile(r"[（(]\s*([0-9]{3}[0-9A-Z]|[A-Z]{1,5})\s*[)）]")


# ---------- what the raw already has ----------

def own_inputs(found: dict) -> dict:
    price = VS.price_data(found["price"])
    per_share = VS.per_share_data(found["per_share"])
    rows = [r for r in VS.kv_rows(found["price"]) if not r[0].startswith(("株価", "時価総額"))]
    return {"shares": price["shares"], "currency": price["currency"], "old_date": price["date"],
            "eps_actual": (per_share["eps_actual"] or {}).get("value"),
            "eps_forecast": (per_share["eps_forecast"] or {}).get("value"),
            "bps": (per_share["bps"] or {}).get("value"), "kept_rows": rows, "file": found["price"].path}


def _peer_row(row: list[str], col: dict) -> dict:
    def cell(key: str) -> str:
        i = col[key]
        return row[i] if i is not None and i < len(row) else ""
    price, cap = VS.number(cell("株価")), VS.money(cell("時価総額"))

    def per_share(column: str, ratio: str) -> float | None:
        """The column, else the old price ÷ the old ratio (a 6章 without the per-share columns)."""
        value, shown = VS.number(cell(column)), VS.number(cell(ratio))
        return value if value is not None else (price / shown if price and shown else None)
    return {"name": cell("会社").replace("*", "").strip(), "shares": cap[0] / price if cap and price else None,
            "currency": cap[1] if cap else "円", "eps_actual": per_share("EPS（実績）", "PER（実績）"),
            "eps_forecast": per_share("EPS（予想）", "PER（予想）"), "bps": per_share("BPS", "PBR")}


def peer_inputs(found) -> list[dict]:
    """competitors 6章: name, the share count (前回の時価総額 ÷ 前回の株価) and the per-share numbers."""
    out = []
    for table in M.tables(found.body or ""):
        header = [h.replace("*", "").strip() for h in table[0]]
        col = {k: next((i for i, h in enumerate(header) if h.startswith(k)), None) for k in PEER_HEADER}
        if col["会社"] is not None and col["株価"] is not None and col["時価総額"] is not None:
            out += [_peer_row(row, col) for row in table[1:]]
    return out


def peer_codes(company) -> dict[str, str]:
    """name -> code of the 採用 rows of 競合 1.2 (the newest competitors.md that has them)."""
    for _, path in raw_files(company, "competitors"):
        codes = {}
        for table in M.tables(path.read_text(encoding="utf-8")):
            header = [h.strip() for h in table[0]]
            cols = [next((i for i, h in enumerate(header) if h.startswith(w)), None) for w in ("会社", "コード", "判定")]
            if None in cols:
                continue
            name_col, code_col, judge_col = cols
            for row in table[1:]:
                m = CODE.match(row[code_col]) if code_col < len(row) else None
                if m and judge_col < len(row) and row[judge_col].strip().startswith("採用"):
                    codes[row[name_col].replace("*", "").strip()] = m.group(1)
        if codes:
            return codes
    return {}


def _code_of(codes: dict[str, str], name: str) -> str | None:
    """The code of 1.2, else the one written in the name ('アルファ社（1111）')."""
    hit = next((c for n, c in codes.items() if same_company(n, name)), None)
    m = NAME_CODE.search(name)
    return hit or (m.group(1) if m else None)


# ---------- prices ----------

def closes(symbol: str, today: str, get, now: int | None) -> dict[str, float]:
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    rows, _ = SP.fetch(symbol, start, today, get, now)
    return {r["date"]: float(r["close"]) for r in rows if r.get("close")}


def _fmt_price(value: float, currency: str) -> str:
    return f"{value:,.2f}ドル" if currency == "ドル" else f"{value:,.0f}円"


def _fmt_cap(value: float, currency: str) -> str:
    return f"{value / 1e6:,.0f}百万{'ドル' if currency == 'ドル' else '円'}"


def _ratio(price: float, per_share: float | None) -> str:
    return f"{price / per_share:.2f}倍" if per_share and per_share > 0 else "—（EPS・BPS が無いかマイナス）"


def _per_share(value: float | None, currency: str) -> str:
    return "—" if value is None else (f"{value:,.2f}ドル" if currency == "ドル" else f"{value:,.2f}円")


# ---------- the files ----------

HEADER_NOTE = ("> 確度の定義: 一次＝会社・取引所・官公庁の原本 / 二次＝IRBANK・株探・EDINET DB 等の転載・集計 / "
               "検索要約＝Web検索結果の要約のみで原本未確認\n> 取得できなかった項目は `—` とし、理由を併記する。数値は記載値の転記"
               "（単位・会計期間を明記）。")


def valuation_text(name: str, today: str, base: str, symbol: str, own: dict, price: float, prev_rel: str) -> str:
    cur = own["currency"]
    rows = [f"| 株価 | {_fmt_price(price, cur)} | 基準日 {base} の確定終値。Yahoo Finance チャート API、取得 {today}（二次） |",
            f"| 時価総額 | {_fmt_cap(price * own['shares'], cur)}（= {_fmt_price(price, cur)} × {own['shares']:,.0f}株） | "
            "自己株式を除く株式数ベースの計算値 |"]
    rows += [f"| {label} | {value} | {note} |" for label, value, note in own["kept_rows"]]
    return "\n".join([
        f"# 株価・バリュエーションデータ — {name}", "",
        f"**収集日**: {today}", "**情報源**:",
        f"- Yahoo Finance チャート API（https://query1.finance.yahoo.com/v8/finance/chart/{symbol}）{today} 取得。"
        f"{base} の確定終値 — 確度: 二次",
        f"- 株式数・EPS・BPS は前回ファイル {prev_rel} の値（refresh_valuation.py が転記）",
        "**原本**: なし（株価は API の値）", "",
        f"前回ファイル: {prev_rel} からの差分（1章・3章。refresh_valuation.py が株価だけを取り直した）", "",
        HEADER_NOTE, "",
        "## 1. 現在の株価・時価総額・株式数", "| 項目 | 値 | 基準日時・出典 |", "|---|---|---|", *rows, "",
        "## 3. 現在の株価指標", "| 指標 | 値 |", "|---|---|",
        f"| PER（実績／予想） | {_ratio(price, own['eps_actual'])} ／ {_ratio(price, own['eps_forecast'])}"
        "（= 株価 ÷ 前回ファイル 2章の EPS） |",
        f"| PBR | {_ratio(price, own['bps'])}（= 株価 ÷ 前回ファイル 2章の BPS） |", ""])


def _competitor_row(p: dict) -> str:
    cur = p["currency"]
    cells = [p["name"], _fmt_price(p["price"], cur), _fmt_cap(p["price"] * p["shares"], cur),
             _ratio(p["price"], p["eps_actual"]), _ratio(p["price"], p["eps_forecast"]), _ratio(p["price"], p["bps"]),
             EV_NOTE, _per_share(p["eps_actual"], cur), _per_share(p["eps_forecast"], cur), _per_share(p["bps"], cur)]
    return "| " + " | ".join(cells) + " |"


def competitors_text(name: str, today: str, base: str, peers: list[dict], prev_rel: str) -> str:
    return "\n".join([
        f"# 競合・同業他社 — {name}", "",
        f"**収集日**: {today}", "**情報源**:",
        f"- Yahoo Finance チャート API {today} 取得。{base} の確定終値（自社と同じ基準日）— 確度: 二次",
        f"- 株式数（前回の時価総額 ÷ 前回の株価）・EPS・BPS は前回ファイル {prev_rel} 6章の値",
        "**原本**: なし（株価は API の値）", "",
        f"前回ファイル: {prev_rel} からの差分（6章。refresh_valuation.py が株価だけを取り直した）", "",
        HEADER_NOTE, "",
        f"## 6. PER・PBR・EV/EBITDA（基準日 {base}）",
        f"<!-- 株価は {base} の確定終値（自社と同じ日）。時価総額 = 株価 × 株式数（前回ファイルの時価総額 ÷ 株価）。"
        "PER・PBR = 株価 ÷ 前回ファイルの EPS・BPS。EV/EBITDA は分析スクリプトが 11章・12章から計算する -->",
        "| " + " | ".join(PEER_HEADER) + " |", "|" + "---|" * len(PEER_HEADER), *map(_competitor_row, peers), ""])


def update_status(path: Path, today: str, base: str, raw_rel: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    new = re.sub(r"^\| 株価・株価指標 \|[^|\n]*\|[^|\n]*\|[^|\n]*\|", f"| 株価・株価指標 | {base} 終値 | {today} | {raw_rel} |",
                 text, count=1, flags=re.M)
    if new == text:
        return False
    new = re.sub(r"^(\*\*最終更新\*\*: [^\n]*?)\s*$", rf"\1（{today} に株価のみ更新: refresh_valuation.py）", new, count=1,
                 flags=re.M)
    atomic_write_text(path, new)
    return True


def append_history(path: Path, today: str, base: str, peers: list[dict]) -> bool:
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("## 情報収集履歴")), None)
    last = None if start is None else max((i for i in range(start, len(lines)) if lines[i].startswith("| 20")),
                                          default=None)
    if last is None:
        return False
    names = "、".join(p["name"] for p in peers) or "—"
    lines.insert(last + 1, f"| {today} | update | 株価 {base} 終値のみ | {names} | refresh_valuation.py（エージェントなし） |")
    atomic_write_text(path, "\n".join(lines) + "\n")
    return True


# ---------- run ----------

def _fail(error: str, **extra) -> dict:
    return {"ok": False, "error": error, "fallback": FALLBACK, **extra}


def _inputs(company) -> tuple[dict | None, list[dict], dict, dict | None]:
    """(own, peers, found, error)."""
    found = VI.gather_valuation(company)
    for key in ("price", "per_share", "peer_valuation"):
        if found[key].status != "ok":
            return None, [], found, _fail(f"{found[key].spec.label} が raw に無い（株価だけの更新はできない）")
    own = own_inputs(found)
    if not own["shares"]:
        return None, [], found, _fail("株価データ 1章に自己株式を除く株式数が無い")
    peers, codes = peer_inputs(found["peer_valuation"]), peer_codes(company)
    for p in peers:  # the company's own row of 6章, when written, is rewritten with its own close
        p["own"] = VS._is_own(p["name"], company)
        p["code"] = company.ticker if p["own"] else _code_of(codes, p["name"])
    missing = [p["name"] for p in peers if not p["shares"] or not p["code"]]
    if not peers or missing:
        return None, [], found, _fail("競合の銘柄コード（1.2 の採用の行）か前回の株価・時価総額が無い", peers_missing=missing)
    return own, peers, found, None


def run(root: Path, company_arg: str, today: str, get=http_get, now: int | None = None) -> dict:
    path = SP.company_dir(root, company_arg)
    if path is None:
        return {"ok": False, "error": f"companies/ に「{company_arg}」の企業が無い"}
    company = VP.Company(root, path)
    val_path = path / "raw" / "ir" / f"{today}_valuation-data.md"
    comp_path = path / "raw" / "market" / f"{today}_competitors.md"
    if val_path.exists() or comp_path.exists():
        return {"ok": False, "error": f"今日（{today}）の valuation-data.md か competitors.md がすでにある", "fallback": None}
    own, peers, found, error = _inputs(company)
    if error:
        return error
    symbol = SP.symbol_for(company.ticker)
    try:
        own_closes = closes(symbol, today, get, now)
        for p in peers:
            p["symbol"] = SP.symbol_for(p["code"])
            p["closes"] = closes(p["symbol"], today, get, now)
    except (ProviderError, OSError, ValueError, RuntimeError) as exc:  # requests errors subclass OSError
        return _fail(f"株価を取得できなかった: {exc}")
    common = sorted(set(own_closes).intersection(*(p["closes"] for p in peers)))
    if not common:
        return _fail("自社と競合の確定終値がそろう日が直近に無い", symbols=[symbol] + [p["symbol"] for p in peers])
    base = common[-1]
    if own["old_date"] and base <= own["old_date"]:
        return {"ok": False, "error": f"確定終値の最新日 {base} が raw の基準日 {own['old_date']} より新しくない（更新不要）",
                "fallback": None}
    for p in peers:
        p["price"] = p["closes"][base]
    rel = company.rel
    name = company.display_name()
    atomic_write_text(val_path, valuation_text(name, today, base, symbol, own, own_closes[base], rel(own["file"])))
    atomic_write_text(comp_path, competitors_text(name, today, base, peers, rel(found["peer_valuation"].path)))
    others = [p for p in peers if not p["own"]]
    return {"ok": True, "base_date": base, "price": own_closes[base], "symbol": symbol,
            "peers": [{"name": p["name"], "symbol": p["symbol"], "price": p["price"]} for p in others],
            "files": [rel(val_path), rel(comp_path)],
            "status_updated": update_status(path / "status.md", today, base, val_path.relative_to(path).as_posix()),
            "history_added": append_history(path / "overview.md", today, base, others)}


def main(argv: list[str] | None = None, root: Path = REPO_ROOT, get=http_get) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", required=True, help="銘柄コード・企業ディレクトリ名")
    parser.add_argument("--date", help="YYYY-MM-DD（今日の代わり。テスト用）")
    args = parser.parse_args(argv)
    today = args.date or dt.date.today().isoformat()
    result = run(root, args.company, today, get, None if args.date else int(time.time()))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
