"""{date}_swot.md: skeleton, parse, checks and the conclusion (SWOT Yes / 条件付き / No / 判定保留).

企業分析フレームワーク.md 1-4, decided here (not by the writer):
  必ず記載する項目 (手順1): every five-forces factor rated 強 is a threat (T), every moat left by the moat
    analysis (effective_moats) is a strength (S). build refuses an md that leaves one out.
  最大の強み / 最大の脅威 (手順2): the strength is picked among the 大 items, the threat among the 大 items
    (中 when there is no 大). build checks the picks against the impact column.
  SWOT の結論 (手順3), first match wins:
    判定保留: every strength or every threat is rated 不明, or no threat is 大/中 while one is 不明
              (material missing; distinct from No, and 不明 is never read as the favourable 小)
    No:       no strength rated 大 (nothing to stand against the threat)
    Yes:      no threat rated 大 or 中
    otherwise the writer's answer (Yes / 条件付き / No); 条件付き needs the company's measure.
"""
from __future__ import annotations

import re
from string import Template

import mdparse as M
from ff_doc import CHANGED_FROM_PREVIOUS, CONFIDENCE, LOW_CONFIDENCE, TIE_BREAK, _check_words, replace_section
from sw_metrics import scale_note, scale_rows
from validate import check_fill, check_structure, check_tables

QUADRANTS = (("S", "2.1", "強み"), ("W", "2.2", "弱み"), ("O", "2.3", "機会"), ("T", "2.4", "脅威"))
QUADRANT_NAME = {q: name for q, _, name in QUADRANTS}
ORIGINS = ("1-1", "1-2", "1-3", "中計", "リスク", "業界", "地合い", "財務", "事業")
IMPACTS = ("大", "中", "小", "不明")
LARGE, MEDIUM, UNKNOWN = "大", "中", "不明"
ANSWERS = ("Yes", "条件付き", "No")
PHRASE = {"Yes": "耐えられる", "条件付き": "条件付きで耐えられる", "No": "耐えられない"}
PENDING = "判定保留"
NONE = "なし"
ROW_COLUMNS = 8
DETAIL_LIMIT = 120  # characters of an upstream reason shown in 1.1
DIGIT = re.compile(r"[0-9０-９]")


# ---------- 必ず記載する項目 ----------

def required_items(five_forces: tuple[str, dict] | None, moat: tuple[str, dict] | None) -> list[dict]:
    """Five-forces factors rated 強 -> T, moats left by the moat analysis -> S (the framework's rule)."""
    out = []
    for f in (five_forces[1].get("factors", []) if five_forces else []):
        if f.get("rating") == "強" and f.get("name"):
            out.append({"quadrant": "T", "tag": "1-1", "name": f.get("name", ""),
                        "detail": f"強: {f.get('reason', '')}"})
    if moat:
        basis = {m.get("type"): m.get("basis", "") for m in moat[1].get("moats", [])}
        for name in filter(None, moat[1].get("effective_moats", [])):
            out.append({"quadrant": "S", "tag": "1-3", "name": name, "detail": f"該当: {basis.get(name, '')}"})
    return out


def cell(text: str, limit: int | None = None) -> str:
    text = (text or "—").replace("|", "／").replace("\n", " ").strip() or "—"
    return text if limit is None or len(text) <= limit else text[:limit].rstrip() + "…"


def required_rows(items: list[dict]) -> str:
    if not items:
        return "| — | — | 必ず記載する項目なし（ファイブフォースに「強」の要因なし、モートの該当なし） |"
    return "\n".join(f"| {QUADRANT_NAME[i['quadrant']]}（{i['quadrant']}） | {i['tag']} {i['name']} | "
                     f"{cell(i['detail'], DETAIL_LIMIT)} |" for i in items)


# ---------- skeleton ----------

def _previous(previous: tuple[str, dict] | None) -> tuple[str, str]:
    """(前回の最大の強み・脅威, 前回の判定)."""
    if not previous:
        return "—（初回）", "—（初回）"
    date, r = previous
    top = f"強み {(r.get('top_strength') or {}).get('id', NONE)}・脅威 {(r.get('top_threat') or {}).get('id', NONE)}"
    return f"{top}（{date}）", f"{r.get('answer', '—')}（結論 {r.get('verdict', '—')}。{date}）"


def render_skeleton(template: str, values: dict, items: list[dict], scale: dict | None,
                    previous: tuple[str, dict] | None) -> str:
    prev_top, prev_answer = _previous(previous)
    filled = dict(values, required_rows=required_rows(items), scale_rows=scale_rows(scale),
                  scale_note=scale_note(scale), prev_top=prev_top, prev_answer=prev_answer)
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    return {r.get("項目", ""): r.get("内容", "") for r in M.table_dicts(text)}


def _quadrant_rows(text: str, number: str) -> list[dict]:
    tables = M.tables(M.section(text, number, level=3))
    rows = [row + [""] * (ROW_COLUMNS - len(row)) for row in tables[0][1:]] if tables else []
    return [{"id": r[0].strip(), "origin": r[1].strip(), "fact": r[2], "basis": r[3], "source": r[4],
             "confidence": r[5].strip(), "impact": r[6].strip(), "impact_reason": r[7]} for r in rows]


def parse(text: str) -> dict:
    top, answer, handoff = _kv(M.section(text, "4.")), _kv(M.section(text, "5.")), _kv(M.section(text, "7."))
    return {
        "quadrants": {q: _quadrant_rows(text, number) for q, number, _ in QUADRANTS},
        "top_strength": top.get("最大の強み", "").strip(), "top_strength_reason": top.get("最大の強みを選んだ理由", ""),
        "top_threat": top.get("最大の脅威", "").strip(), "top_threat_reason": top.get("最大の脅威を選んだ理由", ""),
        "answer": answer.get("判定", "").strip(), "answer_reason": answer.get("理由", ""),
        "measure": answer.get("必要な対策", ""), "sentence": answer.get("結論の文", ""),
        "step2_checks": handoff.get("STEP 2 で確かめること", ""), "summary": handoff.get("企業分析レポートでの要約", ""),
        "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "8.")), "gaps": M.bullets(M.section(text, "9.")),
    }


def items_of(parsed: dict, quadrant: str) -> list[dict]:
    """The quadrant's rows, without the single 'なし' row."""
    rows = parsed["quadrants"][quadrant]
    return [] if rows and rows[0]["id"] == NONE else rows


def _find(parsed: dict, quadrant: str, item_id: str) -> dict | None:
    return next((r for r in items_of(parsed, quadrant) if r["id"] == item_id), None)


# ---------- checks ----------

def _check_row(quadrant: str, row: dict, seen: set[str]) -> list[str]:
    where = f"{QUADRANT_NAME[quadrant]} {row['id'] or '（番号なし）'}"
    issues = []
    if not re.fullmatch(rf"{quadrant}\d+", row["id"]):
        issues.append(f"{where}: 番号は {quadrant}1, {quadrant}2, … の形にする")
    elif row["id"] in seen:
        issues.append(f"{where}: 番号が重複している")
    seen.add(row["id"])
    if not row["origin"].startswith(ORIGINS):
        issues.append(f"{where}: 由来は {' / '.join(ORIGINS)} のいずれかで始める: 「{row['origin']}」")
    for label, key in (("事実", "fact"), ("根拠（数値）", "basis"), ("情報源", "source"), ("影響度の理由", "impact_reason")):
        if M.is_blank(row[key]):
            issues.append(f"{where}: {label}が空")
    if row["confidence"] not in CONFIDENCE:
        issues.append(f"{where}: 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{row['confidence']}」")
    if row["impact"] not in IMPACTS:
        issues.append(f"{where}: 影響度は {'/'.join(IMPACTS)} の1語: 「{row['impact']}」")
    elif row["impact"] in (LARGE, MEDIUM) and not DIGIT.search(row["impact_reason"]):
        issues.append(f"{where}: 影響度「{row['impact']}」の理由に、影響する金額か比率（数値）と3章の目安を書く。"
                      "書けなければ「不明」にする")
    return issues


def _check_quadrant(quadrant: str, rows: list[dict]) -> list[str]:
    name = QUADRANT_NAME[quadrant]
    if not rows:
        return [f"{name}の表に行が無い（無ければ1行だけ「なし」）"]
    if rows[0]["id"] == NONE:
        issues = [] if len(rows) == 1 else [f"{name}: 「なし」の行は1行だけにする（項目があるなら「なし」の行を消す）"]
        return issues + ([f"{name} なし: 事実の列に確認した材料を書く"] if M.is_blank(rows[0]["fact"]) else [])
    seen: set[str] = set()
    return [issue for row in rows for issue in _check_row(quadrant, row, seen)]


def _names_item(origin: str, item: dict) -> bool:
    """'1-1 新規参入の脅威' / '1-1 新規参入の脅威（強）' name the item; '1-1 参入' or another tag does not."""
    if not origin.startswith(item["tag"]):
        return False
    rest = origin[len(item["tag"]):].strip()
    return rest == item["name"] or rest.startswith(item["name"] + "（") or rest.startswith(item["name"] + " ")


def check_required(parsed: dict, items: list[dict]) -> list[str]:
    issues = []
    for i in items:
        rows = items_of(parsed, i["quadrant"])
        if not any(_names_item(r["origin"], i) for r in rows):
            issues.append(f"{QUADRANT_NAME[i['quadrant']]}（{i['quadrant']}）に必ず記載する項目が無い: 由来「{i['tag']} "
                          f"{i['name']}」の行を書く（1.1 を参照）")
    return issues


def eligible(parsed: dict, quadrant: str) -> list[str]:
    """Ids that may be picked as the biggest strength (大) or threat (大, else 中)."""
    rows = items_of(parsed, quadrant)
    large = [r["id"] for r in rows if r["impact"] == LARGE]
    if large or quadrant == "S":
        return large
    return [r["id"] for r in rows if r["impact"] == MEDIUM]


def _check_pick(parsed: dict, quadrant: str, key: str, label: str) -> list[str]:
    pick, allowed = parsed[key], eligible(parsed, quadrant)
    rule = "影響度「大」" if quadrant == "S" else "影響度「大」（無ければ「中」）"
    issues = [] if not M.is_blank(parsed[f"{key}_reason"]) else [f"4. {label}を選んだ理由が空"]
    if pick == NONE:
        if allowed:
            issues.append(f"4. {label}: {rule}の項目 {', '.join(allowed)} があるので「なし」にしない")
        return issues
    if not _find(parsed, quadrant, pick):
        return issues + [f"4. {label}: {QUADRANT_NAME[quadrant]}の表に無い番号「{pick}」（番号1つか「なし」）"]
    if pick not in allowed:
        issues.append(f"4. {label}: {pick} は{rule}ではない（選べるのは {', '.join(allowed) or 'なし'}）")
    return issues


def pending_reasons(parsed: dict) -> list[str]:
    out = []
    for quadrant in ("S", "T"):
        rows = items_of(parsed, quadrant)
        if rows and all(r["impact"] == UNKNOWN for r in rows):
            out.append(f"{QUADRANT_NAME[quadrant]}の影響度がすべて不明")
    threats = items_of(parsed, "T")
    if (not eligible(parsed, "T") and any(r["impact"] == UNKNOWN for r in threats)
            and not all(r["impact"] == UNKNOWN for r in threats)):
        out.append("中以上の脅威は無いが、影響度が不明の脅威がある（良い方に解釈して Yes にしない）")
    return out


def forced_answer(parsed: dict) -> tuple[str | None, str]:
    """(answer the rules fix, why), or (None, '') when the writer's judgement decides."""
    if pending_reasons(parsed):
        return None, ""
    if parsed["top_strength"] == NONE:
        return "No", "影響度「大」の強みが無い（最大の脅威に対抗できる強みが無い）"
    if parsed["top_threat"] == NONE:
        return "Yes", "影響度が中以上の脅威が無い"
    return None, ""


def _check_answer(parsed: dict) -> list[str]:
    answer = parsed["answer"]
    if answer not in ANSWERS:
        return [f"5. 判定は {'/'.join(ANSWERS)} の1語: 「{answer}」"]
    issues = [] if not M.is_blank(parsed["answer_reason"]) else ["5. 理由が空"]
    forced, why = forced_answer(parsed)
    if forced and answer != forced:
        issues.append(f"5. 判定: {why}ので「{forced}」にする（結論の文もそれに合わせる）")
    if answer == "条件付き" and M.is_blank(parsed["measure"]):
        issues.append("5. 条件付きなのに必要な対策（会社の施策と出典）が空。施策が見当たらなければ No にする")
    sentence = parsed["sentence"]
    if not ("により" in sentence and f"に対して{PHRASE[answer]}" in sentence and "理由" in sentence):
        issues.append(f"5. 結論の文は「〈最大の強み〉により、〈最大の脅威〉に対して{PHRASE[answer]}。理由：〇〇」の形にする")
    return issues


def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("7. STEP 2 で確かめること", p["step2_checks"]), ("7. 企業分析レポートでの要約", p["summary"]),
            ("7. 評価が変わる条件", p["triggers"])]


def validate(text: str, template: str, items: list[dict]) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    for quadrant, _, _ in QUADRANTS:
        issues += _check_quadrant(quadrant, p["quadrants"][quadrant])
    issues += check_required(p, items)
    issues += _check_pick(p, "S", "top_strength", "最大の強み") + _check_pick(p, "T", "top_threat", "最大の脅威")
    issues += _check_answer(p)
    if not p["changes"]:
        issues.append("8. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("9. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


def check_reference(parsed: dict, previous: tuple[str, dict] | None) -> list[str]:
    """An answer that differs from the previous result needs「前回から変更:」."""
    if not previous:
        return []
    prev = previous[1].get("answer")
    if prev and parsed["answer"] != prev and CHANGED_FROM_PREVIOUS not in parsed["answer_reason"]:
        return [f"5. 判定: 前回「{prev}」から変えたので、理由に「{CHANGED_FROM_PREVIOUS}:」を書く"]
    return []


# ---------- conclusion ----------

def _pick(parsed: dict, quadrant: str, key: str) -> dict:
    row = _find(parsed, quadrant, parsed[key])
    if not row:
        return {"id": NONE, "fact": "", "impact": ""}
    return {"id": row["id"], "fact": row["fact"], "impact": row["impact"]}


def judge(parsed: dict) -> dict:
    strength, threat = _pick(parsed, "S", "top_strength"), _pick(parsed, "T", "top_threat")
    pending = pending_reasons(parsed)
    forced, why = forced_answer(parsed)
    if pending:
        verdict, why = PENDING, "、".join(pending) + "（材料不足。No とは区別する）"
    elif forced:
        verdict = forced
    else:
        verdict, why = parsed["answer"], parsed["answer_reason"]
    return {"verdict": verdict, "why": why, "top_strength": strength, "top_threat": threat}


def _pick_cell(pick: dict) -> str:
    return NONE if pick["id"] == NONE else f"{pick['id']} {cell(pick['fact'])}（影響度 {pick['impact']}）"


def conclusion_section(judged: dict, sentence: str) -> str:
    if judged["verdict"] == PENDING:  # the writer's sentence states an answer the rules did not adopt
        sentence = f"（書き手の暫定の見方: {sentence}）" if not M.is_blank(sentence) else ""
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 最大の強み | {_pick_cell(judged['top_strength'])} |",
        f"| 最大の脅威 | {_pick_cell(judged['top_threat'])} |",
        f"| SWOT の結論 | **{judged['verdict']}**: {cell(judged['why'])} {cell(sentence)} |"])


def apply_conclusion(text: str, judged: dict, sentence: str) -> str:
    return replace_section(text, "6.", conclusion_section(judged, sentence))


def flags(parsed: dict) -> dict:
    """Items the completion report lists: tie breaks, reference-only evidence and 不明 impacts."""
    rows = [r for quadrant, _, _ in QUADRANTS for r in items_of(parsed, quadrant)]
    return {"tie_breaks": [r["id"] for r in rows if TIE_BREAK in r["impact_reason"]]
            + (["5. 判定"] if TIE_BREAK in parsed["answer_reason"] else []),
            "low_confidence": [r["id"] for r in rows if r["confidence"] == LOW_CONFIDENCE],
            "unknown": [r["id"] for r in rows if r["impact"] == UNKNOWN]}
