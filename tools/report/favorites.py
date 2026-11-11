"""favorites: the ledger of companies whose company report runs on a schedule (GitHub Actions).

Usage:
  favorites.py list
  favorites.py add      --company X --group A|B
  favorites.py remove   --company X
  favorites.py move     --company X --group A|B
  favorites.py validate
  favorites.py targets  --group A|B

--company takes '3798', '3798_uls-group' or part of the directory name.
The ledger is companies/favorites.json, written only by this script (tools/guard/write_guard.py blocks hand
edits by the agent, and its digest exposes edits made outside the agent). Group A runs at 0:30 JST and group B
at 6:00 JST on weekdays (.github/workflows/company-report.yml); each group holds at most MAX_PER_GROUP
companies, and only a company with a built report (reports/{date}_company-report.json) can be added.
targets: the directory names of one group for the workflow (validated first).
stdout is one JSON line so the calling agent spends few tokens. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path[:0] = [str(TOOLS / "analysis"), str(TOOLS / "collect")]

import an_common as A  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

LEDGER = Path("companies") / "favorites.json"
GROUPS = ("A", "B")
MAX_PER_GROUP = 5
VERSION = 1
REPORT_JSON = "_company-report.json"
DIGEST_PREFIX = "sha256:"


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


# ---------- ledger ----------

def empty_groups() -> dict[str, list[dict]]:
    return {g: [] for g in GROUPS}


def digest(groups: dict) -> str:
    canonical = json.dumps(groups, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return DIGEST_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load(root: Path) -> tuple[dict | None, str | None]:
    """(ledger, error). A missing ledger is an empty one."""
    path = root / LEDGER
    if not path.exists():
        return {"version": VERSION, "groups": empty_groups(), "updated": None, "digest": digest(empty_groups())}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{LEDGER.as_posix()} を読めない: {exc}"
    if not isinstance(data, dict) or not isinstance(data.get("groups"), dict):
        return None, f"{LEDGER.as_posix()} の形式が違う（groups が無い）"
    return data, None


def save(root: Path, groups: dict, today: str) -> dict:
    ledger = {"version": VERSION, "groups": groups, "updated": today, "digest": digest(groups)}
    atomic_write_text(root / LEDGER, json.dumps(ledger, ensure_ascii=False, indent=1) + "\n")
    return ledger


def built_reports(root: Path, dirname: str) -> list[str]:
    """Dates of the built company reports of a company, oldest first."""
    return [date for date, _ in A.dated_files(root / "companies" / dirname / "reports", REPORT_JSON)]


def group_of(groups: dict, dirname: str) -> str | None:
    return next((g for g in GROUPS if any(e.get("company") == dirname for e in groups.get(g, []))), None)


def issues(root: Path, ledger: dict) -> list[str]:
    """Everything that makes the ledger unusable: hand edits, unknown groups, limits, duplicates, missing reports."""
    groups = ledger.get("groups", {})
    found = []
    if ledger.get("digest") != digest(groups):
        found.append(f"{LEDGER.as_posix()} が手で書き換えられている（digest が一致しない）。"
                     "favorites スキル（favorites.py）で登録し直す")
    found += [f"未知のグループ {g}（{'/'.join(GROUPS)} だけ）" for g in groups if g not in GROUPS]
    seen: dict[str, str] = {}
    for g in GROUPS:
        entries = groups.get(g, [])
        if not isinstance(entries, list):
            found.append(f"グループ {g} が配列でない")
            continue
        if len(entries) > MAX_PER_GROUP:
            found.append(f"グループ {g} が {len(entries)} 社（上限 {MAX_PER_GROUP} 社）")
        for entry in entries:
            name = entry.get("company", "") if isinstance(entry, dict) else ""
            if name in seen:
                found.append(f"{name} がグループ {seen[name]} と {g} の両方にある")
            seen[name] = g
            if not name or not (root / "companies" / name).is_dir():
                found.append(f"グループ {g} の {name or '（空）'} は companies/ に無い")
            elif not built_reports(root, name):
                found.append(f"グループ {g} の {name} は企業分析レポートが一度も build されていない")
    return found


# ---------- helpers ----------

def _today(args: argparse.Namespace) -> str:
    return getattr(args, "date", None) or dt.date.today().isoformat()


def _resolve(root: Path, arg: str) -> tuple[A.Company | None, dict | None]:
    company, candidates = A.resolve_company(root, arg, A.Company)
    if company:
        return company, None
    if candidates:
        return None, {"ok": False, "error": f"「{arg}」に複数の企業が当たる", "candidates": candidates}
    return None, {"ok": False, "error": f"companies/ に「{arg}」の企業が無い"}


def _usable(root: Path) -> tuple[dict | None, dict | None]:
    """The ledger when it is valid; otherwise the error payload (no change is made on an invalid ledger)."""
    ledger, error = load(root)
    if error:
        return None, {"ok": False, "error": error}
    found = issues(root, ledger)
    if found:
        return None, {"ok": False, "error": "台帳に問題がある", "issues": found}
    return ledger, None


def _with(groups: dict, group: str, entry: dict) -> dict:
    return {g: [*groups.get(g, []), entry] if g == group else list(groups.get(g, [])) for g in GROUPS}


def _without(groups: dict, dirname: str) -> dict:
    return {g: [e for e in groups.get(g, []) if e.get("company") != dirname] for g in GROUPS}


def _rows(root: Path, groups: dict) -> dict:
    out = {}
    for g in GROUPS:
        out[g] = []
        for entry in groups.get(g, []):
            dates = built_reports(root, entry["company"])
            out[g].append({**entry, "report_date": dates[-1] if dates else None})
    return out


def _addable(root: Path, groups: dict, company: A.Company, group: str) -> str | None:
    if len(groups.get(group, [])) >= MAX_PER_GROUP:
        return f"グループ {group} は既に {MAX_PER_GROUP} 社（上限）。先に remove か move する"
    if not built_reports(root, company.dirname):
        return (f"{company.dirname} は企業分析レポートを一度も作っていない（reports/*{REPORT_JSON} が無い）。"
                "先に /company-report で作る")
    return None


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    ledger, error = load(root)
    if error:
        return emit({"ok": False, "error": error})
    return emit({"ok": True, "groups": _rows(root, ledger["groups"]), "max_per_group": MAX_PER_GROUP,
                 "updated": ledger.get("updated"), "issues": issues(root, ledger)})


def cmd_add(args: argparse.Namespace, root: Path) -> int:
    ledger, error = _usable(root)
    if error:
        return emit(error)
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    groups = ledger["groups"]
    current = group_of(groups, company.dirname)
    if current:
        return emit({"ok": False, "error": f"{company.dirname} は既にグループ {current} にある（付け替えは move）"})
    reason = _addable(root, groups, company, args.group)
    if reason:
        return emit({"ok": False, "error": reason})
    today = _today(args)
    saved = save(root, _with(groups, args.group, {"company": company.dirname, "added": today}), today)
    return emit({"ok": True, "added": company.dirname, "group": args.group, "groups": _rows(root, saved["groups"])})


def cmd_remove(args: argparse.Namespace, root: Path) -> int:
    ledger, error = load(root)
    if error:
        return emit({"ok": False, "error": error})
    company, error = _resolve(root, args.company)
    # a company whose directory is gone can still be removed by its exact directory name
    dirname = company.dirname if company else args.company.strip().replace("\\", "/").rstrip("/").split("/")[-1]
    current = group_of(ledger["groups"], dirname)
    if not current:
        return emit(error or {"ok": False, "error": f"{dirname} はお気に入りに無い"})
    saved = save(root, _without(ledger["groups"], dirname), _today(args))
    return emit({"ok": True, "removed": dirname, "group": current, "groups": _rows(root, saved["groups"]),
                 "issues": issues(root, saved)})


def cmd_move(args: argparse.Namespace, root: Path) -> int:
    ledger, error = _usable(root)
    if error:
        return emit(error)
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    groups = ledger["groups"]
    current = group_of(groups, company.dirname)
    if not current:
        return emit({"ok": False, "error": f"{company.dirname} はお気に入りに無い（登録は add）"})
    if current == args.group:
        return emit({"ok": False, "error": f"{company.dirname} は既にグループ {current} にある"})
    reason = _addable(root, groups, company, args.group)
    if reason:
        return emit({"ok": False, "error": reason})
    entry = next(e for e in groups[current] if e.get("company") == company.dirname)
    saved = save(root, _with(_without(groups, company.dirname), args.group, entry), _today(args))
    return emit({"ok": True, "moved": company.dirname, "from": current, "group": args.group,
                 "groups": _rows(root, saved["groups"])})


def cmd_validate(args: argparse.Namespace, root: Path) -> int:
    ledger, error = _usable(root)
    if error:
        return emit(error)
    return emit({"ok": True, "counts": {g: len(ledger["groups"].get(g, [])) for g in GROUPS}})


def cmd_targets(args: argparse.Namespace, root: Path) -> int:
    ledger, error = _usable(root)
    if error:
        return emit(error)
    return emit({"ok": True, "group": args.group,
                 "companies": [e["company"] for e in ledger["groups"].get(args.group, [])]})


def main(argv: list[str] | None = None, root: Path = A.REPO_ROOT) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("list", "add", "remove", "move", "validate", "targets"):
        p = sub.add_parser(name)
        if name in ("add", "remove", "move"):
            p.add_argument("--company", required=True, help="銘柄コード・企業ディレクトリ名・社名の一部")
            p.add_argument("--date", help="YYYY-MM-DD（今日の代わり）")
        if name in ("add", "move", "targets"):
            p.add_argument("--group", required=True, choices=GROUPS)
    args = parser.parse_args(argv)
    if getattr(args, "date", None):
        try:
            dt.date.fromisoformat(args.date)
        except ValueError:
            return emit({"ok": False, "error": f"--date は YYYY-MM-DD で指定する: {args.date}"})
    handler = {"list": cmd_list, "add": cmd_add, "remove": cmd_remove, "move": cmd_move,
               "validate": cmd_validate, "targets": cmd_targets}[args.cmd]
    return handler(args, root)


if __name__ == "__main__":
    sys.exit(main())
