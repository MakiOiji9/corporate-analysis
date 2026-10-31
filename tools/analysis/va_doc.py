"""{date}_valuation.md: skeleton, parse, checks and the conclusion (STEP 3 割安/妥当/割高/判定保留).

Every number and every judgement of 企業分析フレームワーク.md STEP 3 comes from va_metrics; the writer only fills
the background (特別損益の中身, PBR の改善策の有無, PER と EV/EBITDA の食い違いの背景, 割安の理由, 7〜9章).
The improvement-measures answer (あり / なし / 不明) is the one input that can change a judgement: build reads it,
recomputes everything from the raw and writes 6章 and the 判定シート row, so an edited table cannot change the
conclusion.
"""
from __future__ import annotations

import re
from string import Template

import mdparse as M
import va_metrics as X
import va_rules as R
from cf_doc import APPROXIMATE
from ff_doc import FIXED_MARK, _check_words, replace_section
from sf_doc import NUMBER, _significant
from validate import check_fill, check_structure, check_tables

NOT_APPLICABLE = "該当なし"
MEASURE_CHOICE = re.compile(r"^\s*(あり|なし|不明)\s*[:：]")
SHEET_ROW = re.compile(r"^\| 判定シートの STEP 3 \|.*\|$", re.M)
FILL_SPECIAL = ("<!-- FILL:special-bg 特別損益の中身を1文（brief の有報「特別利益・特別損失」から、科目と金額・一時的と"
                "いえる理由）。分からなければ「不明（brief に記載なし）」 -->")
FILL_MEASURES = ("<!-- FILL:measures 「あり: 根拠」「なし: 根拠」「不明: 根拠」のどれかで始める。brief の中期経営計画・"
                 "有報の資本政策に ROE・資本効率の改善策（ROE 目標、資本コストを意識した経営、自社株買い・増配など"
                 "株主還元の強化）が示されているか。根拠は出典の資料名と記述を引用する。記載が無ければ「なし」、"
                 "材料が無ければ「不明」 -->")
FILL_DIVERGENCE = ("<!-- FILL:divergence-bg 食い違いの理由を1〜2文。左の「数値からの候補」を brief の記述（手元資金・"
                   "設備投資・借入の方針）で確かめる。理由が brief に無ければ「不明（brief に記載なし）」 -->")
FILL_CHEAP = ("<!-- FILL:cheap-reason 市場がこの会社を安く評価している理由を1〜2文。brief の SWOT の脅威・STEP 2 の"
              "懸念・地合いの記述から説明する。説明できなければ「不明（brief に記載なし）」。STEP 3 が割安で"
              "なければ（6章で build が確定）「該当なし」と書いてよい -->")


def _cell(text: str) -> str:
    return text.replace("|", "／").replace("\n", " ").strip() or "—"


# ---------- 0章 ----------

def base_rows(cands: dict) -> str:
    base = cands["base"]
    price, step1, ev = base["price"], cands["per"]["step1"], cands["ev"]
    cur, unit = price["currency"], base["years"]["unit"]
    forecast = base["forecast_eps"]
    bps = base["per_share"]["bps"]
    rows = [
        ("株価", X.yen(price["price"], cur), f"{price['date'] or '基準日不明'}（{price['source'] or '株価データ 1章'}）"),
        ("発行済株式数（自己株式を除く）", f"{price['shares']:,.0f}株" if price["shares"] else "—",
         price["shares_source"] or "株価データ 1章に記載なし"),
        (f"時価総額（{unit}）", X.amount((ev["market_cap"] or {}).get("value")),
         (ev["market_cap"] or {}).get("basis", "年次の単位にそろえられない")),
        (f"実績EPS（{step1['year'] or '—'}）", R.fmt(step1["eps"], "", 2), step1["source"] or "—"),
        ("予想EPS", R.fmt(forecast["value"], "", 2) if forecast else "—", forecast["label"] if forecast else "記載なし"),
        ("BPS", R.fmt(bps["value"], "", 2) if bps else "—",
         (f"{bps['source']}「{bps['label']}」" if bps.get("source") else f"株価データ 2章「{bps['label']}」") if bps
         else "記載なし"),
        (f"有利子負債 ／ 現金及び現金同等物（{ev['year'] or '—'}、{unit}）", f"{X.amount(ev['debt'])} ／ {X.amount(ev['cash'])}",
         "財務時系列・有報（安全性分析と同じ読み方）"),
        (f"営業利益 ／ 減価償却費（{ev['year'] or '—'}、{unit}）",
         f"{X.amount(ev['operating_income'])} ／ {X.amount(ev['depreciation'])}", "財務時系列・有報（CF 計算書の減価償却費）"),
    ]
    return "\n".join(f"| {_cell(a)} | {_cell(b)} | {_cell(c)} |" for a, b, c in rows)


def history_rows(cands: dict) -> str:
    base = cands["base"]
    ev = {h["year"]: h for h in cands["ev"]["history"]}
    rows = base["history"][-10:]
    if not rows:
        return "| — | — | — | — | — | — | — | 株価データ 4章に年次の倍率が無い |"
    return "\n".join(
        f"| {h['year']} | {R.fmt(h['per_high'])} | {R.fmt(h['per_low'])} | {R.fmt(h['per_end'])} | "
        f"{R.fmt(h['pbr_high'], '倍', 2)} | {R.fmt(h['pbr_low'], '倍', 2)} | "
        f"{R.fmt((ev.get(h['year']) or {}).get('high'))} | {R.fmt((ev.get(h['year']) or {}).get('low'))} |" for h in rows)


def _ev_cell(p: dict) -> str:
    if p.get("ev_ebitda_calc") is not None:
        return f"{p['ev_ebitda_calc']:.1f}倍（算出）"
    return R.fmt(p.get("ev_ebitda"))


def peer_rows(name: str, cands: dict) -> str:
    base = cands["base"]
    own, peers = base["peers"]["own"], base["peers"]["peers"]
    lines = [f"| **{name}** | {R.fmt(cands['per']['per_actual'])} | {R.fmt(cands['per']['per_forecast'])} | "
             f"{R.fmt(cands['pbr']['pbr'], '倍', 2)} | {R.fmt(cands['ev']['value'])} | {R.fmt(own['cagr'], '%')} | "
             f"{R.fmt(own['roe'], '%')} |"]
    lines += [f"| {_cell(p['name'])} | {R.fmt(p['per_actual'])} | {R.fmt(p['per_forecast'])} | "
              f"{R.fmt(p['pbr'], '倍', 2)} | {_ev_cell(p)} | {R.fmt(p['cagr'], '%')} | {R.fmt(p['roe'], '%')} |"
              for p in peers]
    if not peers:
        lines.append("| 競合 | — | — | — | — | — | 競合 6章に同業の倍率が無い |")
    return "\n".join(lines)


def base_note(cands: dict) -> str:
    peer_date = cands["base"]["peers"]["date"] or "不明"
    return ("注: 自社の PER・PBR・EV/EBITDA はスクリプトが株価の基準日の株価から計算（PER = 株価 ÷ EPS、PBR = 株価 ÷ BPS、"
            "EV = 時価総額 + 有利子負債 − 現金及び現金同等物、EBITDA = 営業利益 + 減価償却費）。時価総額は 株価 × 自己株式を"
            "除く株式数。EPS は株式分割を調整した値。過去の EV/EBITDA は「年次の PER の高値・安値 × その年の純利益"
            "（赤字の年は PBR × 自己資本）+ 有利子負債 − 現金」÷ EBITDA で算出した値。"
            f"競合の倍率は競合 6章（基準日 {peer_date}）の株価 ÷ EPS・BPS（列が無い会社は 6章の表示値）、競合の EV/EBITDA は 6章の時価総額・11章の有利子負債と現金・"
            "12章の営業利益と減価償却費からの算出値（無ければ 6章の記載値）。売上高の3年CAGR は競合 3章、ROE は競合 5章。")


# ---------- 1〜5章 ----------

def rating_cell(rating: str, basis: str) -> str:
    return f"{rating}{FIXED_MARK}: {basis}" if rating in (R.LOW, R.FAIR, R.HIGH, R.NA) else f"{rating}: {basis}"


def per_cells(cands: dict) -> dict:
    per = cands["per"]
    s1, rule = per["step1"], per["rule"]
    kind = "調整" if s1["adjusted"] else ""
    na = per["rating"] == R.NA
    ref = "（参考。PER は評価対象外）" if na else ""
    return {
        "per_step1": _cell(s1["sentence"]),
        "special_bg": FILL_SPECIAL if s1["adjusted"] else f"{NOT_APPLICABLE}（EPS を調整していない）",
        "per_step2": _cell(f"実績PER {R.fmt(per['per_actual'])}（株価 ÷ {kind}実績EPS）／予想PER {R.fmt(per['per_forecast'])}"
                           f"（株価 ÷ 予想EPS）。{per['note'] or '—'}"),
        "per_axis1": _cell(rule["axis1"]["basis"] + ref), "per_axis2": _cell(rule["axis2"]["basis"] + ref),
        "per_step4": _cell(f"評価対象外（{per['na']}）" if na else "適用できる（赤字・営業赤字・50%以上の減益に当たらない）"),
        "per_rating": _cell(rating_cell(per["rating"], per["na"] or rule["basis"])),
    }


def pbr_pending(cands: dict) -> bool:
    """The writer's answer decides the PBR judgement (PBR 1倍割れ・ROE 8%未満 and 割安 before the trap check)."""
    pbr = cands["pbr"]
    return pbr["trap"]["applies"] and pbr["before_trap"] == R.LOW


def pbr_cells(cands: dict) -> dict:
    pbr = cands["pbr"]
    rule, trap = pbr["rule"], pbr["trap"]
    pending = pbr_pending(cands)
    if trap["applies"]:
        step3 = (f"該当（PBR {pbr['pbr']:.2f}倍で1倍割れ、ROE {trap['roe']:.1f}%で8%未満）。"
                 + ("改善策が示されていなければ割安とみなさず妥当にする" if pending
                    else "手順2までの判定が割安でないため、判定は変わらない"))
    else:
        step3 = f"{NOT_APPLICABLE}（PBR 1倍以上、または ROE 8%以上）"
    if pending:
        rating = "割安（改善策が「あり」の場合）／妥当（「なし」「不明」の場合）。6章で build が確定"
    else:
        rating = rating_cell(pbr["rating"], pbr["sentence"].split("。", 1)[-1])
    return {
        "pbr_axis1": _cell(rule["axis1"]["basis"]), "pbr_axis2": _cell(rule["axis2"]["basis"]),
        "pbr_step1": _cell(f"{rule['rating']}: {rule['basis']}"), "pbr_step2": _cell(pbr["fair"]["basis"]),
        "pbr_step3": _cell(step3),
        "measures": FILL_MEASURES if pending else f"{NOT_APPLICABLE}（判定に影響しない）",
        "pbr_rating": _cell(rating),
    }


def peg_cells(cands: dict) -> dict:
    peg = cands["peg"]
    names = "、".join(f"{c['name']} {c['value']:.1f}%" for c in peg["candidates"]) or "—（候補なし）"
    cases = peg["cases"]
    labels = (("standard", "標準（最小）"), ("pessimistic", "悲観（標準の半分）"), ("optimistic", "楽観（最大）"))
    case_text = "／".join(f"{label} {R.fmt(cases[k], '%')}（PEG {R.fmt(peg['peg'][k], '倍', 2)}）" for k, label in labels)
    if peg["rating"] in (R.LOW, R.FAIR, R.HIGH):
        margin = "安全域あり（悲観ケースでも2倍以下）" if peg["margin"] else "安全域なし（悲観ケースで2倍超）"
    else:
        margin = "—（PEG を判定していない）"
    step1 = (f"評価対象外（{peg['na']}）" if peg["na"]
             else "適用できる（PER が機能し、成長率5%以上、過去5年に利益の半減なし）")
    return {"peg_step1": _cell(step1), "peg_candidates": _cell(names), "peg_cases": _cell(case_text),
            "peg_rating": _cell(rating_cell(peg["rating"], peg["sentence"])), "peg_margin": margin}


def ev_cells(cands: dict) -> dict:
    ev, per = cands["ev"], cands["per"]
    unit = cands["base"]["years"]["unit"]
    cap = (ev["market_cap"] or {}).get("value")
    parts = (f"時価総額 {X.amount(cap)} + 有利子負債 {X.amount(ev['debt'])} − 現金 {X.amount(ev['cash'])} = "
             f"EV {X.amount(ev['ev'])}（{unit}。{ev['year'] or '—'} 期末の残高）")
    sens = ev.get("sensitivity")
    if sens:
        parts += (f"。株式数が未確定のため、上限の {sens['shares']:,.0f}株（自己株式を含む）では時価総額 "
                  f"{X.amount(sens['market_cap'])}、EV/EBITDA {sens['value']:.1f}倍で {sens['rating']}"
                  f"（{'判定が変わる' if sens['changes'] else '判定は同じ'}）")
    ebitda = (f"営業利益 {X.amount(ev['operating_income'])} + 減価償却費 {X.amount(ev['depreciation'])} = "
              f"EBITDA {X.amount(ev['ebitda'])}")
    rule, div = ev["rule"], ev["divergence"]
    divergence = (f"{div['pattern']}。{div['lead']}。数値からの候補: {'、'.join(div['reasons'])}" if div
                  else f"食い違いなし（PER {per['rating']} ／ EV/EBITDA {ev['rating']}）")
    none = "—（EV/EBITDA を計算していない）"
    return {"ev_parts": _cell(parts), "ebitda_parts": _cell(ebitda),
            "ev_axis1": _cell(rule["axis1"]["basis"] if rule else none),
            "ev_axis2": _cell(rule["axis2"]["basis"] if rule else none),
            "ev_rating": _cell(rating_cell(ev["rating"], ev["sentence"])), "divergence": _cell(divergence),
            "divergence_bg": FILL_DIVERGENCE if div else f"{NOT_APPLICABLE}（食い違いなし）"}


def _score(rating: str) -> str:
    return f"{R.SCORE[rating]:+d}" if rating in R.SCORE else "—（集計から除外）"


def score_cells(cands: dict, alt: dict | None) -> dict:
    """alt: the candidates with the improvement measures answered あり (only when that answer matters)."""
    rows = []
    for key, name in X.INDICATORS:
        rating = cands[key]["rating"]
        if key == "pbr" and alt is not None:
            rows.append(f"| {name} | {alt['pbr']['rating']} または {rating}（2章の改善策の回答で決まる） | "
                        f"{_score(alt['pbr']['rating'])} ／ {_score(rating)} |")
        else:
            rows.append(f"| {name} | {rating} | {_score(rating)} |")
    s3 = cands["step3"]
    if alt is not None:
        a3 = alt["step3"]
        average = (f"改善策「あり」なら {a3['basis']} → {a3['raw_verdict']}／「なし」「不明」なら {s3['basis']} → "
                   f"{s3['raw_verdict']}")
        final = f"「あり」なら {a3['why']}／「なし」「不明」なら {s3['why']}"
    else:
        average = s3["basis"]
        final = s3["why"] if s3["final_check"]["applies"] else f"{NOT_APPLICABLE}（割安でないため不要）"
    cheap = any(c is not None and c["step3"]["raw_verdict"] == R.LOW for c in (cands, alt))
    return {"score_rows": "\n".join(rows), "average": _cell(average), "final_check": _cell(final),
            "cheap_reason": FILL_CHEAP if cheap else f"{NOT_APPLICABLE}（STEP 3 が割安でない）"}


def sheet_cell(cands: dict) -> str:
    peg = cands["peg"]
    pess = R.fmt(peg["peg"]["pessimistic"], "倍", 2) if peg["rating"] in (R.LOW, R.FAIR, R.HIGH) else "—"
    avg = f"{cands['step3']['average']:+.2f}" if cands["step3"]["average"] is not None else "—"
    return _cell(f"PER {cands['per']['rating']}／PBR {cands['pbr']['rating']}／PEG {peg['rating']}（悲観ケース：{pess}）／"
                 f"EV/EBITDA {cands['ev']['rating']}／STEP 3 {cands['verdict']}（平均点：{avg}）")


def render_skeleton(template: str, values: dict, cands: dict, alt: dict | None = None) -> str:
    filled = dict(values, base_rows=base_rows(cands), history_rows=history_rows(cands),
                  peer_rows=peer_rows(values["company"], cands), base_note=base_note(cands),
                  **per_cells(cands), **pbr_cells(cands), **peg_cells(cands), **ev_cells(cands),
                  **score_cells(cands, alt), sheet=sheet_cell(cands),
                  flip_prices=_cell("。".join(cands["flip_prices"]) or "—（計算できる指標なし）"))
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    out = {}
    for table in M.tables(text):
        if table and table[0][:2] == ["項目", "内容"]:
            out.update({row[0]: row[1] if len(row) > 1 else "" for row in table[1:] if row})
    return out


def parse(text: str) -> dict:
    s1, s2, s4, s5, s7 = (_kv(M.section(text, n)) for n in ("1.", "2.", "4.", "5.", "7."))
    measures = s2.get("改善策の有無", "")
    m = MEASURE_CHOICE.match(measures)
    return {"special_bg": s1.get("特別損益の中身", ""), "measures": measures, "measures_choice": m.group(1) if m else None,
            "divergence_bg": s4.get("食い違いの背景", ""), "cheap_reason": s5.get("割安の理由", ""),
            "report_points": s7.get("レポートで使う要点", ""), "final_checks": s7.get("総合判断で確かめること", ""),
            "changes": M.bullets(M.section(text, "8.")), "gaps": M.bullets(M.section(text, "9."))}


def _script_value(value: str) -> bool:
    return value.strip().startswith(NOT_APPLICABLE)


def _written(p: dict) -> list[tuple[str, str]]:
    """(label, text) of every part the writer filled (the script's 該当なし cells excluded)."""
    cells = [("1. 特別損益の中身", p["special_bg"]), ("2. 改善策の有無", p["measures"]),
             ("4. 食い違いの背景", p["divergence_bg"]), ("5. 割安の理由", p["cheap_reason"]),
             ("7. レポートで使う要点", p["report_points"]), ("7. 総合判断で確かめること", p["final_checks"])]
    cells = [(label, v) for label, v in cells if not _script_value(v)]
    return cells + [("8. 前回からの変更点", c) for c in p["changes"]] + [("9. 判定に効く欠損", g) for g in p["gaps"]]


def check_numbers(text: str, reference: str) -> list[str]:
    """Numbers the writer wrote that are in neither the brief nor the script's part of the md, and approximations."""
    written = _written(parse(text))
    script_part = text
    for _, value in written:
        if value:
            script_part = script_part.replace(value, "")
    known = (reference + "\n" + script_part).replace(",", "")
    issues = []
    for label, value in written:
        missing = sorted({n for m in NUMBER.finditer(value or "") if (n := _significant(m.group(0))) and n not in known})
        if missing:
            issues.append(f"{label}: 数値 {'・'.join(missing)} が brief・md に無い（新しく計算しない。brief の値を引用する）")
        if APPROXIMATE.search(value or ""):
            issues.append(f"{label}: 概数（約〜・〜割）を書かない。表の数値をそのまま引用する")
    return issues


def validate(text: str, template: str, cands: dict, reference: str = "") -> list[str]:
    """cands: the candidates recomputed with the writer's measures answer."""
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in (("7. レポートで使う要点", p["report_points"]),
                                                ("7. 総合判断で確かめること", p["final_checks"])) if M.is_blank(value)]
    if cands["per"]["step1"]["adjusted"] and (M.is_blank(p["special_bg"]) or _script_value(p["special_bg"])):
        issues.append("1. 特別損益の中身が空（EPS を調整したので中身を書く）")
    if pbr_pending(cands) and p["measures_choice"] is None:
        issues.append("2. 改善策の有無は「あり: 」「なし: 」「不明: 」のどれかで始める")
    if cands["ev"]["divergence"] and (M.is_blank(p["divergence_bg"]) or _script_value(p["divergence_bg"])):
        issues.append("4. 食い違いの背景が空（PER と EV/EBITDA の判定が逆向き）")
    if cands["step3"]["raw_verdict"] == R.LOW and (M.is_blank(p["cheap_reason"]) or _script_value(p["cheap_reason"])):
        issues.append("5. 割安の理由が空（STEP 3 の平均点が割安。市場が安く評価している理由を書く）")
    if reference:
        issues += check_numbers(text, reference)
    if not p["changes"]:
        issues.append("8. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("9. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- conclusion ----------

def conclusion_section(cands: dict) -> str:
    rows = ["| 項目 | 内容 |", "|---|---|"]
    rows += [f"| {name} | {_cell(cands[key]['rating'] + ': ' + cands[key]['sentence'])} |" for key, name in X.INDICATORS]
    rows.append(f"| 境界に近い比較 | {_cell('。'.join(cands['borderline']) or 'なし')} |")
    rows.append(f"| STEP 3 | **{cands['verdict']}**: {_cell(cands['why'])} |")
    return "\n".join(rows)


def apply_conclusion(text: str, cands: dict) -> str:
    text = replace_section(text, "6.", conclusion_section(cands))
    return SHEET_ROW.sub(lambda _: f"| 判定シートの STEP 3 | {sheet_cell(cands)} |", text, count=1)


def flags(parsed: dict, cands: dict) -> dict:
    """Items the completion report lists."""
    unknown = [label for label, value in _written(parsed) if value.strip().startswith("不明")]
    return {"unknown_backgrounds": unknown, "borderline": cands["borderline"],
            "measures": parsed["measures_choice"] if cands["pbr"]["trap"]["applies"] else None}
