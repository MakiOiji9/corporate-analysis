"""FILL markers of the analysis md: list them, prefill the mechanical ones, and pour a writer's JSON into them.

prepare writes the skeleton with every <!-- FILL:key hint --> marker; the fields that follow from the numbers
(前回からの変更点, 欠損, 引き継ぎの定型文, 該当なしの欄) are filled by the script here (prefill), so the writer
only gets the background text. The writer may then put {key: text} in one JSON file and run `fill`, instead of
reading the whole md and editing each marker.

A marker on a table row ("| 項目 | <!-- FILL:x ... --> |") is a cell: the text is put on one line and "|" is
replaced by "｜" so the table keeps its columns. A marker on a line of its own is a block (bullets, table rows)
and keeps its line breaks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

FILL_MARKER = re.compile(r"<!--\s*FILL:([\w-]+)([^>]*)-->")  # the hints never contain ">"
NOT_FILLED = "なし"


def _line_of(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    return text[start:] if end < 0 else text[start:end]


def fill_spec(text: str) -> list[dict]:
    """Every marker in order: key, the instruction and whether it is a table cell."""
    out = []
    for m in FILL_MARKER.finditer(text):
        out.append({"key": m.group(1), "hint": m.group(2).strip(),
                    "cell": _line_of(text, m.start()).lstrip().startswith("|")})
    return out


def fill_keys(text: str) -> list[str]:
    return [m.group(1) for m in FILL_MARKER.finditer(text)]


def _cell(value: str) -> str:
    return " ".join(value.split()).replace("|", "｜")


def _block(value: str) -> str:
    return value.strip("\n")


def substitute(text: str, values: dict[str, str]) -> tuple[str, list[str]]:
    """Replace the markers whose key is in values; returns the text and the keys replaced."""
    used: list[str] = []

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            return m.group(0)
        used.append(key)
        cell = _line_of(m.string, m.start()).lstrip().startswith("|")
        return _cell(values[key]) if cell else _block(values[key])

    return FILL_MARKER.sub(repl, text), used


def prefill(text: str, values: dict[str, str | None]) -> str:
    """Fill the markers the script can write (a None value leaves the marker for the writer)."""
    return substitute(text, {k: v for k, v in values.items() if v is not None and v.strip()})[0]


def fill_at_build(text: str, keys: tuple[str, ...], compute) -> str:
    """Fields derived from what the writer wrote in the same md (e.g. SWOT の強み候補 from the moat rows): once
    every other FILL is gone, compute(text) -> {key: text} fills the ones still open. While the writer is not
    done the text is returned as is, so a half-written md never freezes a derived field."""
    remaining = set(fill_keys(text))
    if not remaining or remaining - set(keys):
        return text
    return prefill(text, compute(text))


def apply_fills(text: str, fills: object) -> tuple[str, list[str], list[str]]:
    """(new text, keys filled, issues). Nothing is applied when there is an issue."""
    if not isinstance(fills, dict):
        return text, [], ["JSON は {\"FILL のキー\": \"本文\"} のオブジェクトにする"]
    keys = set(fill_keys(text))
    issues = [f"{k}: md に無い FILL のキー（prepare の fill_keys を使う）" for k in fills if k not in keys]
    issues += [f"{k}: 本文が文字列でない、または空" for k, v in fills.items()
               if k in keys and (not isinstance(v, str) or not v.strip())]
    if issues:
        return text, [], issues
    new, used = substitute(text, fills)
    return new, used, []


def load_fills(path: Path) -> tuple[object, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"{path} が無い"
    except (OSError, ValueError) as e:
        return None, f"{path} を JSON として読めない: {e}"


# ---------- text the script writes ----------

def bullets(lines: list[str], empty: str = NOT_FILLED) -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else f"- {empty}"


def _shown(value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def changes_bullets(previous: tuple[str, dict] | None, pairs: list[tuple[str, object, object]]) -> str:
    """「前回からの変更点」: label, previous value, current value. Values that are equal are left out."""
    if not previous:
        return "- 初回の分析"
    changed = [f"{label}: {_shown(old)} → {_shown(new)}（前回 {previous[0]}）"
               for label, old, new in pairs if _shown(old) != _shown(new)]
    return bullets(changed)


STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}


def gaps_bullets(found: dict, warnings: list[str] = (), extra: list[str] = ()) -> str:
    """「判定に効く欠損」: inputs that are not ok, the script's warnings and analysis-specific gaps."""
    rows = [f"{f.spec.label}: {STATUS_LABEL.get(f.status, f.status)}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    rows += [f"警告: {w}" for w in warnings] + list(extra)
    return bullets(rows)


def joined(parts: list[str]) -> str:
    """Sentences joined with 「。」, each ending once."""
    text = "。".join(p.rstrip("。") for p in parts if p)
    return text + "。" if text else ""


def auto_reference(auto: dict[str, str | None]) -> str:
    """The script's own text, for the number checks of build: thresholds the script wrote are not the writer's
    new numbers."""
    return "\n".join(v for v in auto.values() if v)


# ---------- the fill command ----------

def run_fill(md_path: Path, fills_path: Path, write) -> dict:
    """Pour fills_path into md_path (write(path, text) writes atomically). Returns the payload of `fill`."""
    if not md_path.exists():
        return {"ok": False, "error": f"{md_path.name} が無い（先に prepare）"}
    fills, error = load_fills(fills_path)
    if error:
        return {"ok": False, "error": error}
    text = md_path.read_text(encoding="utf-8")
    new, used, issues = apply_fills(text, fills)
    if issues:
        return {"ok": False, "issues": issues, "fill_keys": fill_keys(text)}
    write(md_path, new)
    return {"ok": True, "filled": used, "remaining": fill_keys(new)}


def prepare_fields(company, md_path: Path, build_keys: tuple[str, ...] = ()) -> dict:
    """What prepare returns about the fields left for the writer (company has .rel(path)). build_keys are
    filled by build from the rest of the md (fill_at_build) and are not the writer's."""
    text = md_path.read_text(encoding="utf-8")
    keys = [k for k in fill_keys(text) if k not in build_keys]
    out = {"fill": len(keys), "fill_keys": keys, "fill_spec": [s for s in fill_spec(text) if s["key"] not in build_keys],
           "fills_json": company.rel(default_fills_path(md_path))}
    if build_keys:
        out["filled_at_build"] = [k for k in build_keys if k in fill_keys(text)]
    return out


def cmd_fill(args, root: Path, *, resolve, target, build, name: str, emit, write,
             build_keys: tuple[str, ...] = ()) -> int:
    """The `fill` subcommand of an analysis script: resolve(root, arg) -> (company, error), target(company, date)
    -> (date, md path) | None, build(args, root) -> exit code. build_keys: fields build fills itself."""
    company, error = resolve(root, args.company)
    if error:
        return emit(error)
    found = target(company, args.date)
    if not found:
        return emit({"ok": False, "error": f"{name} が無い（先に prepare）"})
    md_path = found[1]
    payload = run_fill(md_path, Path(args.source) if args.source else default_fills_path(md_path), write)
    if payload["ok"]:
        payload["remaining"] = [k for k in payload["remaining"] if k not in build_keys]
    if payload["ok"] and args.build and not payload["remaining"]:
        return build(args, root)
    return emit({**payload, "md": company.rel(md_path)})


def add_fill_args(parser) -> None:
    parser.add_argument("--from", dest="source",
                        help="書き手の JSON（{\"FILL のキー\": \"本文\"}）。省略時は md と同じ場所の {日付}_fills.json")
    parser.add_argument("--build", action="store_true", help="流し込んで FILL が残らなければ、続けて build する")


def default_fills_path(md_path: Path) -> Path:
    """{date}_{kind}.md -> {date}_fills.json next to it (the writer's JSON; not committed)."""
    return md_path.with_name(md_path.name.split("_", 1)[0] + "_fills.json")
