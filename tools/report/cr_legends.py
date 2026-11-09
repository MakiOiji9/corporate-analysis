"""投資の神の視点（参考）: Buffett・Soros・Rogers の考え方を facts.json に当てはめ、好む / 避ける / 保留 を決める.

The rules are those of .ai/knowledge/legendary-investors/{buffett,soros,rogers}.md (sections 5・6); change both
together. The view is a reference beside the report's verdicts: it never enters the horizon scores. Each check is
{id, item, value, ok, source} with ok True (the investor's condition is met) / False / None (no material).
The writer only explains the result in the md (5章); build checks the verdict word and the wording.
"""
from __future__ import annotations

import re

import cr_factors as F
import cr_judge as J

PREFER, HOLD, AVOID = "好む", "保留", "避ける"
VERDICT_CLASS = {PREFER: "v-consider", HOLD: "v-watch", AVOID: "v-pass"}
LEGENDS = (  # key, full name, short name, horizon, one-line philosophy
    ("buffett", "ウォーレン・バフェット", "バフェット", "長期",
     "理解できる優れた事業を、妥当な価格で買い、長く持つ"),
    ("soros", "ジョージ・ソロス", "ソロス", "短期〜中期",
     "市場の思い込みと現実のずれ（再帰性）に乗り、誤りに気づいたらすぐ引く"),
    ("rogers", "ジム・ロジャーズ", "ロジャーズ", "中期〜長期",
     "誰も見向きしない安いものを、前向きな変化が見えたときに買い、何年も待つ"),
)
KEYS = tuple(k for k, *_ in LEGENDS)
NAMES = {k: name for k, name, *_ in LEGENDS}
SHORT = {k: short for k, _, short, *_ in LEGENDS}
PHRASE = "の考え方に当てはめると"
ROW = re.compile(r"^\| (" + "|".join(NAMES.values()) + r")（.*$", re.M)
CLAIM = re.compile(r"(?:バフェット|ソロス|ロジャーズ)(?:なら|は|が)(?:この会社|同社|当社|この株)?を?(?:買う|売る|保有する)")
DOC = ".ai/knowledge/legendary-investors/{key}.md"
OK_MARK = {True: "○", False: "×", None: "不明"}

NEAR_TERM = "5年以内"
CF_RATIO_MIN = 0.8
DROP_FROM_HIGH = -20.0  # 52週高値からの下落（バフェットの「悲観で安くなっている」の添え書き）
MOVE = 5.0  # 売上の前年同期比・26週移動平均との差が ±5% を超えたら向きありとみなす
LONG_LOW = 33.0  # 5年・10年レンジの位置がこれ以下なら長く安い
HOT_ZONE = 80.0  # 52週レンジの位置がこれ以上で割高なら熱狂
FCF_YEARS = 5
UP, DOWN, MIXED, FLAT, UNKNOWN = "上向き", "下向き", "混在", "横ばい", "不明"


def _check(cid: str, item: str, value: object, ok: bool | None, source: str) -> dict:
    return {"id": cid, "item": item, "value": "—" if value in (None, "") else str(value), "ok": ok,
            "source": source}


def _known(word: str | None) -> bool:
    return bool(word) and word != J.PENDING


def _word(word: str | None) -> str:
    return word or "未実施"


def _detail(a: dict) -> dict:
    return a.get("detail") or {}


def _range(prices: dict, label: str) -> dict | None:
    return next((w for w in prices.get("ranges") or [] if w.get("label") == label), None)


def _average_gap(prices: dict, label: str) -> float | None:
    return next((a.get("gap") for a in prices.get("averages") or [] if a.get("label") == label), None)


def _sales_yoy(facts: dict) -> float | None:
    items = (_detail(facts["analyses"]["growth"]).get("progress") or {}).get("items") or {}
    return (items.get("sales") or {}).get("yoy")


def _result(verdict: str, why: str, checks: list[dict], notes: list[str], **extra: str) -> dict:
    return {"verdict": verdict, "why": why, "checks": checks, "notes": notes, **extra}


# ---------------------------------------------------------------- Buffett (buffett.md 5・6章)

def _fcf_total(cash_flow: dict) -> float | None:
    values = [r["fcf"] for r in _detail(cash_flow).get("rows") or [] if r.get("fcf") is not None]
    return sum(values[-FCF_YEARS:]) if values else None


def _b4(prof: dict, safety: dict) -> bool | None:
    pv, sv = prof["verdict"], safety["verdict"]
    if not (_known(pv) and _known(sv)):
        return None
    return pv == "良好" and sv in ("良好", "普通") and "借入" not in (_detail(prof).get("source") or "")


def _b6(cf: dict) -> bool | None:
    cv, ratio, fcf = cf["verdict"], _detail(cf).get("ratio"), _fcf_total(cf)
    if not _known(cv):
        return None
    return cv == "良好" or (cv == "普通" and ratio is not None and ratio >= CF_RATIO_MIN and fcf is not None and fcf > 0)


def _buffett_checks(facts: dict) -> list[dict]:
    a = facts["analyses"]
    moat, prof, safety, cf, growth = a["moat"], a["profitability"], a["safety"], a["cash_flow"], a["growth"]
    near = [r.get("factor") or "—" for r in _detail(moat).get("risks") or [] if NEAR_TERM in (r.get("timing") or "")]
    mv, tv, gv, s3 = moat["verdict"], a["three_c"]["verdict"], growth["verdict"], facts["step3"]["verdict"]
    roe, src = _detail(prof).get("roe_average"), _detail(prof).get("source")
    ratio, fcf, plan = _detail(cf).get("ratio"), _fcf_total(cf), _detail(growth).get("plan")
    w52 = _range(facts["prices"], "52週") or {}
    overall = facts["outlook"].get("overall")
    pessimism = overall == "警戒" or (w52.get("from_high") or 0) <= DROP_FROM_HIGH
    return [
        _check("B1", "変化の速い業界ではないか", f"5年以内に堀を崩しうる要因: {'・'.join(near) or 'なし'}",
               None if not _known(mv) else not near, "1-3 モート（崩しうる要因）"),
        _check("B2", "長く続く競争優位（モート）", _word(mv), {"広い": True, "なし": False}.get(mv), "1-3 モート"),
        _check("B3", "勝てる理由", _word(tv), {"明確": True, "あいまい": False, "なし": False}.get(tv), "1-2 3C"),
        _check("B4", "借金に頼らない高い ROE",
               f"収益性 {_word(prof['verdict'])}（ROE 10年平均 {roe if roe is not None else '—'}%、源泉 {src or '—'}）"
               f"・安全性 {_word(safety['verdict'])}", _b4(prof, safety), "2-1 収益性・2-3 安全性"),
        _check("B5", "一貫した収益力", f"成長性 {_word(gv)}", {"良好": True, "普通": True, "懸念": False}.get(gv),
               "2-2 成長性"),
        _check("B6", "利益が現金で裏付けられている",
               f"キャッシュフロー {_word(cf['verdict'])}（営業CF対純利益 {ratio if ratio is not None else '—'}倍、"
               f"FCF {FCF_YEARS}年累計 {f'{fcf:,.0f}' if fcf is not None else '—'}）", _b6(cf), "2-4 キャッシュフロー"),
        _check("B7", "会社計画の信頼性（経営者）", plan, None if not plan else "割り引" not in plan,
               "2-2 成長性（期初予想の達成率）"),
        _check("B8", "価格に安全域があるか", _word(s3), {"割安": True, "妥当": True, "割高": False}.get(s3),
               "3 バリュエーション"),
        _check("B9", "市場の悲観で安くなっているか（添え書き）",
               f"地合い {overall or '—'}、52週高値から {w52.get('from_high', '—')}%", pessimism, "地合い・株価の過去レンジ"),
    ]


def buffett(facts: dict) -> dict:
    checks = _buffett_checks(facts)
    ok = {c["id"]: c["ok"] for c in checks}
    a = facts["analyses"]
    avoid = [text for cond, text in (
        (a["moat"]["verdict"] == "なし", "モートが「なし」"),
        (a["profitability"]["verdict"] == "懸念", "収益性が「懸念」"),
        (a["safety"]["verdict"] == "懸念", "安全性が「懸念」"),
        (a["cash_flow"]["verdict"] == "懸念", "キャッシュフローが「懸念」"),
        (bool(facts["step2"].get("flags")), "深刻な赤信号がある")) if cond]
    notes = ["市場の悲観で株価が下がっている（事業が基準に合うときだけ好機に数える）"] if ok["B9"] else []
    if avoid:
        return _result(AVOID, "・".join(avoid), checks, notes)
    moat = a["moat"]["verdict"]
    business = ((moat == "広い" or (moat == "狭い" and ok["B4"])) and ok["B1"] is not False
                and all(ok[k] for k in ("B3", "B4", "B6")))
    if business and ok["B8"]:
        return _result(PREFER, f"モート {moat}・勝てる理由 明確・高い ROE と現金の裏付けがあり、株価は "
                               f"{facts['step3']['verdict']}", checks, notes)
    if business:
        return _result(HOLD, "事業は基準に合うが、株価が割高で安全域が無い", checks, notes)
    unmet = [c["item"] for c in checks if c["id"] in ("B1", "B2", "B3", "B4", "B5", "B6") and c["ok"] is not True]
    return _result(HOLD, "満たさない・確かめられない条件: " + "・".join(unmet), checks, notes)


# ---------------------------------------------------------------- Soros (soros.md 5・6章)

def _business_direction(facts: dict) -> tuple[str, str]:
    signals, parts = [], []
    progress = F.progress_factor(facts["analyses"]["growth"])
    if progress["score"] is not None:
        signals.append(progress["score"])
        parts.append(f"営業利益の進捗 {progress['value']}")
    yoy = _sales_yoy(facts)
    if yoy is not None:
        signals.append(1.0 if yoy >= MOVE else -1.0 if yoy <= -MOVE else 0.0)
        parts.append(f"売上 前年同期比 {yoy:+.1f}%")
    if not signals:
        return UNKNOWN, "四半期の進捗が無い"
    direction = (MIXED if 1.0 in signals and -1.0 in signals else UP if 1.0 in signals
                 else DOWN if -1.0 in signals else FLAT)
    return direction, "、".join(parts)


def _price_direction(prices: dict) -> tuple[str, float | None]:
    gap = _average_gap(prices, "26週")
    if gap is None:
        return UNKNOWN, None
    return (UP if gap > MOVE else DOWN if gap < -MOVE else FLAT), gap


def _soros_checks(facts: dict, s1: str, s1_value: str, s3: str, gap: float | None) -> list[dict]:
    s3_word = facts["step3"]["verdict"]
    s2 = {"割高": "高い", "割安": "低い", "妥当": "中程度"}.get(s3_word)
    overall, sv = facts["outlook"].get("overall"), facts["analyses"]["safety"]["verdict"]
    return [
        _check("S1", "現実の流れ（業績）の向き", f"{s1}（{s1_value}）", {UP: True, DOWN: False}.get(s1),
               "2-2 成長性（四半期の進捗）"),
        _check("S2", "市場の期待（評価倍率）の高さ", f"{s2 or UNKNOWN}（STEP 3 {_word(s3_word)}）",
               None if s2 is None else s2 != "高い", "3 バリュエーション"),
        _check("S3", "株価の流れの向き", f"{s3}（26週移動平均との差 {gap if gap is not None else '—'}%）",
               {UP: True, DOWN: False}.get(s3), "株価の過去レンジ"),
        _check("S5", "逆回転を起こしやすい地合いでないか", f"注意の度合い {overall or '—'}",
               None if not overall else overall != "警戒", "地合い"),
        _check("S6", "借入に頼らず逆回転に強いか", f"安全性 {_word(sv)}", None if not _known(sv) else sv != "懸念",
               "2-3 安全性"),
    ]


def soros(facts: dict) -> dict:
    s1, s1_value = _business_direction(facts)
    s3, gap = _price_direction(facts["prices"])
    checks = _soros_checks(facts, s1, s1_value, s3, gap)
    ok = {c["id"]: c["ok"] for c in checks}
    high, reverse, weak = ok["S2"] is False, ok["S5"] is False, ok["S6"] is False
    if high and s1 == DOWN:
        return _result(AVOID, "期待が高い（割高）のに業績が下向きで、現実が期待に追いつけない兆し", checks, [])
    if s3 == DOWN and s1 == DOWN and (reverse or weak):
        return _result(AVOID, "株価と業績がともに下向きで強め合い、地合いか財務が逆回転を増幅しうる", checks, [])
    if s1 == UP and not reverse and (not high or s3 == UP):
        return _result(PREFER, "業績が上向きで、期待がまだ追いついていないか、株価と業績が強め合っている", checks, [])
    why = {MIXED: "業績の材料に上向きと下向きが混ざり、流れの向きが決まらない", FLAT: "業績の流れに向きが無い",
           UNKNOWN: "業績の流れを確かめる材料が無い", DOWN: "業績は下向きだが、期待も株価も行き過ぎていない"}.get(
        s1, "業績は上向きだが、地合いが逆回転を起こしやすいか、期待が高く株価が追いついていない")
    return _result(HOLD, why, checks, [])


# ---------------------------------------------------------------- Rogers (rogers.md 5・6章)

def _changes(facts: dict) -> tuple[bool | None, list[str]]:
    swot = facts["analyses"]["swot"]
    big = [o["id"] for o in (_detail(swot).get("quadrants") or {}).get("O") or [] if o.get("impact") == "大"]
    yoy = _sales_yoy(facts)
    found = [f"{i}（影響度 大）" for i in big] + ([f"売上 前年同期比 {yoy:+.1f}%"] if yoy is not None and yoy >= MOVE else [])
    if not swot.get("verdict") and yoy is None:
        return None, found
    return bool(found), found


def _rogers_checks(facts: dict) -> list[dict]:
    prices, s3 = facts["prices"], facts["step3"]["verdict"]
    long_ranges = [w for w in (_range(prices, "5年"), _range(prices, "10年")) if w]
    lowest = min((w["position"] for w in long_ranges), default=None)
    w52 = _range(prices, "52週")
    per = (_detail(facts["analyses"]["valuation"]).get("items") or {}).get("PER") or {}
    hot = None if not w52 else w52["position"] >= HOT_ZONE and (per.get("rating") == "割高" or s3 == "割高")
    r3, changes = _changes(facts)
    entry = next((f for f in _detail(facts["analyses"]["five_forces"]).get("factors") or []
                  if f.get("name") == "新規参入の脅威"), {})
    long_row = (facts["outlook"].get("rows") or {}).get("長期") or {}
    return [
        _check("R1", "長い目で見て安いか",
               ("、".join(f"{w['label']} {w['position']:.0f}%" for w in long_ranges) + f"（STEP 3 {_word(s3)}）")
               if long_ranges else "株価の時系列が無い",
               None if lowest is None else lowest <= LONG_LOW and s3 != "割高", "株価の過去レンジ・3 バリュエーション"),
        _check("R2", "熱狂していないか",
               f"52週レンジの位置 {w52['position']:.0f}%、PER {per.get('rating') or '—'}" if w52 else "株価の時系列が無い",
               None if hot is None else not hot, "株価の過去レンジ・3 バリュエーション"),
        _check("R3", "前向きな変化", "・".join(changes) or "影響度 大の機会・売上の伸びなし", r3,
               "1-4 SWOT（機会）・2-2 成長性（四半期の進捗）"),
        _check("R4", "業界の需給（新規参入の脅威）", entry.get("rating"),
               None if not entry.get("rating") else entry["rating"] in ("弱", "中"), "1-1 ファイブフォース"),
        _check("R6", "長期の地合い", long_row.get("judgment"),
               None if not long_row.get("judgment") else long_row["judgment"] != "警戒", "地合い（長期の行）"),
    ]


def rogers(facts: dict) -> dict:
    checks = _rogers_checks(facts)
    ok = {c["id"]: c["ok"] for c in checks}
    notes = [f"{c['item']}: {c['value']}" for c in checks if c["id"] in ("R4", "R6")]
    if ok["R2"] is False:
        return _result(AVOID, "株価が高値圏で割高（熱狂）", checks, notes)
    if ok["R1"] and ok["R3"] is False and facts["analyses"]["growth"]["verdict"] == "懸念":
        return _result(AVOID, "長く安いが前向きな変化が無く、業績も下向き（安い理由がある）", checks, notes)
    if ok["R1"] and ok["R3"]:
        return _result(PREFER, "長く安く放置されていて、前向きな変化が起きている", checks, notes)
    why = ("長く安いが、前向きな変化がまだ見えない" if ok["R1"] else
           "前向きな変化はあるが、長い目で見て安くない" if ok["R3"] else "安さと変化のどちらも確かめられない")
    return _result(HOLD, why, checks, notes)


# ---------------------------------------------------------------- facts / md / brief

RULES = {"buffett": buffett, "soros": soros, "rogers": rogers}


def evaluate(facts: dict) -> dict:
    """{key: {name, short, horizon, philosophy, doc, verdict, why, checks, notes}} in LEGENDS order."""
    return {key: {"name": name, "short": short, "horizon": horizon, "philosophy": philosophy,
                  "doc": DOC.format(key=key), **RULES[key](facts)}
            for key, name, short, horizon, philosophy in LEGENDS}


def _cell(text: object) -> str:
    return " ".join(str(text).split()).replace("|", "｜")


def rows(facts: dict) -> str:
    """The md's 5章 table rows (script-owned, like the conclusion table)."""
    return "\n".join(f"| {v['name']}（{v['horizon']}） | {v['verdict']} | {_cell(v['why'])} |"
                     for v in (facts.get("legends") or {}).values())


def brief_lines(facts: dict) -> list[str]:
    legends = facts.get("legends") or {}
    if not legends:
        return []
    lines = ["## 投資の神の視点（md 5章の材料。評価はスクリプトが決めた。変えない）", "",
             f"- 各欄は「〈名前〉{PHRASE}: 〈評価〉。」で書き始め、下の項目から評価の決め手を1つ以上、値を添えて書く。"
             "逆の材料か「不明」の項目を1つ添える",
             "- 本人が実際にこの会社をこう評価した・売買したとは書かない（「〜なら買う」も書かない）。本人の発言を引用しない",
             "- 1章の判定とは別の参考の視点。判定と食い違うときは、何を重く見るかが違うことを1文で書いてよい", ""]
    for v in legends.values():
        lines += [f"### {v['name']}: {v['verdict']}（{v['horizon']}の見方。{v['philosophy']}）", "",
                  f"- 評価の理由: {v['why']}"] + [f"- 添え書き: {n}" for n in v["notes"]]
        lines += ["", "| 項目 | 値 | 満たす | 情報源 |", "|---|---|---|---|"]
        lines += [f"| {c['id']} {c['item']} | {_cell(c['value'])} | {OK_MARK[c['ok']]} | {c['source']} |"
                  for c in v["checks"]]
        lines += ["", f"- 考え方の資料: {v['doc']}（読まなくてよい）", ""]
    return lines


def validate(parsed: dict, table_text: str, facts: dict) -> list[str]:
    legends = facts.get("legends") or {}
    issues = []
    got = [line.strip() for line in table_text.splitlines() if ROW.match(line.strip())]
    if legends and got != rows(facts).splitlines():
        issues.append("5章の投資の神の表がスクリプトの評価と違う（表は変更しない。元に戻す）")
    for key, v in legends.items():
        text = parsed.get(key) or ""
        if not text.strip():
            continue
        if f"{v['short']}{PHRASE}" not in text:
            issues.append(f"{v['name']}の欄は「{v['short']}{PHRASE}: {v['verdict']}。」で書き始める")
        if v["verdict"] not in text:
            issues.append(f"{v['name']}の欄に評価（{v['verdict']}）が無い")
        claim = CLAIM.search(text)
        if claim:
            issues.append(f"{v['name']}の欄: 本人が実際に売買する・評価したとは書かない（「{claim.group(0)}」）")
    return issues
