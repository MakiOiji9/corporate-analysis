import json
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT), str(REPORT.parent / "analysis"), str(REPORT.parent / "collect" / "market"),
                str(REPORT.parent / "collect")]

import cr_winds as W  # noqa: E402
import sector_map as SM  # noqa: E402

OUTLOOK = """# 地合い

## 5. リスク要因

| リスク | 市場 | 影響 | 兆候を確認する指標 | 根拠（情報源） |
|---|---|---|---|---|
| 米国の財政・通商の不確実性 | 日米 | 中 | 関税措置 | 10-28 にロボット・産業機械の輸入調整の布告 |
| 銀行株の下落 | 日本 | 小 | 銀行指数 | 報道 |

## 13. 業種の追い風・向かい風

### 13.1 株価の相対の強さ

| 市場 | 業種 | 6か月 | 指数との差（6か月） | 12か月 | 指数との差（12か月） | 株価の強さ |
|---|---|---|---|---|---|---|
| 日本 | 電機・精密 | -8.0% | -9.0% | -10.0% | -12.0% | 弱い |

### 13.2 政策・通商・金利の材料

| 市場 | 業種 | 方向 | 区分 | 根拠 | 出典 |
|---|---|---|---|---|---|
| 日本 | 電機・精密 | 向かい風 | 通商・規制 | 米国の輸入調整の布告（10-28） | 大統領令一覧 |
| 日本 | 電機・精密 | 追い風 | 金利・為替 | 円安で輸出採算が改善 | 日銀・為替 |
| 日本 | 銀行 | 追い風 | 金利・為替 | 金利上昇 | 日銀 |
"""


def _market(root: Path, week: str = "2026-11-09", outlook: str = OUTLOOK) -> dict:
    report = root / "market" / "report"
    report.mkdir(parents=True)
    (report / f"{week}_outlook.md").write_text(outlook, encoding="utf-8")
    rows = [{"id": "JP_SEC_1625", "name": "電機・精密", "m6": -8.0, "rel6": -9.0, "m12": -10.0, "rel12": -12.0,
             "strength": "弱い"}]
    (report / f"{week}_facts.json").write_text(json.dumps({"sectors": {"japan": {"rows": rows}}}, ensure_ascii=False),
                                               encoding="utf-8")
    return {"path": f"market/report/{week}_outlook.md", "week": week}


def test_sector_map():
    assert SM.sector_id({"market": "japan", "sector_name": "電気機器"}) == "JP_SEC_1625"
    assert SM.sector_id({"market": "japan", "sector_name": "情報・通信業"}) == "JP_SEC_1626"
    assert SM.sector_id({"market": "us", "sic": 3674}) == "US_SEC_XLK"
    assert SM.sector_id({"market": "us", "sic": 6022}) == "US_SEC_XLF"
    assert SM.sector_id({"market": "japan", "sector_name": "不明な業種"}) is None


def test_winds_combine_price_strength_and_written_items(tmp_path):
    outlook = _market(tmp_path)
    w = W.evaluate(tmp_path, {"market": "japan", "sector_name": "電気機器"}, outlook, "産業用ロボット・ACサーボ")
    assert w["ok"] and w["sector"] == "電機・精密" and w["strength"] == "弱い"
    assert [i["direction"] for i in w["items"]] == ["向かい風", "追い風"]  # the bank row is another sector
    assert w["score"] == -1 and w["verdict"] == "向かい風"
    assert any("ロボット" in r for r in w["related"])  # the risk row mentions the business


def test_old_outlook_without_chapter_13(tmp_path):
    outlook = _market(tmp_path, outlook="# 地合い\n\n## 5. リスク要因\n")
    w = W.evaluate(tmp_path, {"market": "japan", "sector_name": "電気機器"}, outlook, "")
    assert w["ok"] and w["items"] == [] and w["strength"] == "弱い" and w["verdict"] == "向かい風"


def test_without_a_sector_or_outlook(tmp_path):
    assert not W.evaluate(tmp_path, {"market": "japan", "sector_name": "?"}, {"path": None}, "")["ok"]
    assert not W.evaluate(tmp_path, {"market": "japan", "sector_name": "電気機器"}, {"path": None}, "")["ok"]


def test_outlook_before_the_strength_column_has_nothing_to_judge(tmp_path):
    outlook = _market(tmp_path, outlook="# 地合い\n")
    facts = tmp_path / "market" / "report" / "2026-11-09_facts.json"
    facts.write_text(json.dumps({"sectors": {"japan": {"rows": [{"id": "JP_SEC_1625", "name": "電機・精密"}]}}},
                                ensure_ascii=False), encoding="utf-8")
    w = W.evaluate(tmp_path, {"market": "japan", "sector_name": "電気機器"}, outlook, "")
    assert not w["ok"] and w["verdict"] == "材料なし"
