"""Reader's words for the company report: the analyses' internal terms become what they mean.

The analyses write for the next script or writer ("手順1が良好", "brief に無い", "market/report/..._outlook.md",
"（collect-peers-valuation）"). The report is read on its own, so plain() turns a step number into the name of
what that step checks, a file path into the document it is, and drops the collection agents' names.
leaks() finds what is left in the visible text of the HTML; build stops on any.
"""
from __future__ import annotations

import html
import re

# 企業分析フレームワーク.md の各分析の手順（「手順N」→ その手順で確かめること）
STEP_NAMES: dict[str, dict[int, str]] = {
    "five_forces": {1: "業界の定義", 2: "5つの要因の評価", 3: "業界の魅力度の結論"},
    "three_c": {1: "顧客の分析", 2: "競合の分析", 3: "自社の分析", 4: "勝てる理由の結論"},
    "moat": {1: "超過収益の確認", 2: "モートの源泉", 3: "持続性と傾向", 4: "モートの結論"},
    "swot": {1: "4象限への振り分け", 2: "影響度の評価", 3: "強みで脅威に対抗できるか"},
    "profitability": {1: "ROE の水準と安定性", 2: "営業利益率の同業比較", 3: "ROE の源泉", 4: "収益性の結論"},
    "growth": {1: "成長の水準", 2: "減収・減益の年の原因", 3: "会社計画の信頼性", 4: "成長の質", 5: "成長性の結論"},
    "safety": {1: "財務の現状の水準", 2: "財務の推移", 3: "借入の目的", 4: "安全性の結論"},
    "cash_flow": {1: "営業CF の安定性", 2: "FCF の創出力", 3: "利益の質", 4: "CF パターン", 5: "株主還元の持続性",
                  6: "キャッシュフローの結論"},
    "valuation": {1: "指標ごとの点数", 2: "平均点", 3: "最終確認"},
}
# 「キャッシュフロー手順1」のように分析名が前に付くもの
LABEL_KEYS = {"ファイブフォース": "five_forces", "3C": "three_c", "モート": "moat", "SWOT": "swot",
              "収益性": "profitability", "成長性": "growth", "安全性": "safety", "キャッシュフロー": "cash_flow",
              "バリュエーション": "valuation"}
# raw/・analysis/ のファイル名の後半 → 読み手の言葉
DOC_LABELS = {"competitors": "競合の資料", "industry-overview": "業界の資料", "business-overview": "事業の資料",
              "yuho": "有価証券報告書", "10-k": "年次報告書（10-K）", "press-releases": "プレスリリース",
              "financials-historical": "過去の業績", "valuation-data": "株価指標の資料", "mid-term-plan": "中期経営計画",
              "positioning": "信用残・空売りの資料", "outlook": "地合いレポート", "five-forces": "ファイブフォース分析",
              "three-c": "3C分析", "moat": "モート分析", "swot": "SWOT分析", "profitability": "収益性分析",
              "growth": "成長性分析", "safety": "安全性分析", "cash-flow": "キャッシュフロー分析",
              "valuation": "バリュエーション分析", "management": "経営者の資料"}
DATA_LABELS = {"prices.csv": "日々の株価", "tdnet_facts.csv": "決算短信", "financials.csv": "財務データ",
               "quarterly.csv": "四半期の業績", "positioning.csv": "信用残・空売りのデータ",
               "consensus.json": "アナリスト予想", "profile.json": "会社の基本情報", "governance.json": "有価証券報告書"}
PHRASES = (("比べる材料が無いため ？ を △ とみなし", "比べる材料が無いため同程度とみなし"),
           ("？ を △ とみなし", "比べる材料が無いため同程度とみなし"), ("？ → △ とみなした", "比べる材料が無く同程度とみなした"),
           ("（status.md の未取得項目）", "（未取得の項目）"), ("（status.md）", ""),
           ("迷った:", "判断が分かれた点:"), ("迷った：", "判断が分かれた点:"), ("手順の規則", "判定の規則"),
 ("（短期の行）", "（短期の見通し）"),
           ("（中期の行）", "（中期の見通し）"), ("（長期の行）", "（長期の見通し）"))
# 読み手に見せない言葉（build が HTML の本文で探す）。出典の人物名もここに入れる。
# 業務の文章（「製造手順」「metadata/」）に当たらないよう、内部の書き方の形だけを探す
INTERNAL_PATTERNS = {
    "手順N": r"手順\s*\d", "brief": r"(?<![A-Za-z])brief(?![A-Za-z])", "迷った": r"迷った",
    "パス": r"(?<![A-Za-z])(?:raw|data|analysis|market/report)/", "ファイル名": r"(?<![\w./-])[\w*-]+\.(?:md|csv)(?![\w])",
    "収集エージェント": r"(?<![A-Za-z])collect-[a-z]", "FILL": r"FILL", "status.md": r"status\.md",
    "出典の人物名": r"清原(?:流|達郎|氏)"}
INTERNAL_TOKENS = tuple(INTERNAL_PATTERNS)
_INTERNAL = {name: re.compile(p) for name, p in INTERNAL_PATTERNS.items()}
_BRIEF = re.compile(r"\s?(?<![A-Za-z])brief(?:\.md)?(?![A-Za-z])\s?")
# fields that name things (companies, ids, years): they are looked up by value elsewhere and stay as they are
NAME_KEYS = frozenset({"name", "id", "key", "year", "self", "type"})
LEAK_LIMIT = 20

_LABELLED_STEP = re.compile("(" + "|".join(map(re.escape, LABEL_KEYS)) + r")(?:分析)?\s*手順\s*(\d)")
_STEP_WITH_NAME = re.compile(r"手順\s*\d（([^（）]{1,15})）")
_STEP = re.compile(r"手順\s*(\d)")
_OUTLOOK = re.compile(r"(?:market/report/)?(\d{4}-\d{2}-\d{2})_outlook\.md")
# paths are ASCII: \w would also eat the Japanese words around them
_PATH = r"[A-Za-z0-9_*/.-]"
_DOC = re.compile(rf"(?:(?:companies/[A-Za-z0-9_.-]+/)?(?:raw|analysis)/{_PATH}*?/)?(?:[0-9*][0-9*-]*_)*"
                  r"([a-z0-9-]+)\.md")
# a section reference is 「8.」 or 「8. 見出し」: a number, a dot and nothing or a space (「5つの…」「3年連続」 stay)
_SECTION_REF = re.compile(r"「\d+(?:\.\d+)*\.(?:\s[^」]{0,40})?」")
_DATA = re.compile(r"(?:companies/[A-Za-z0-9_.-]+/)?data/([A-Za-z0-9_.]+)")
_RAW_LEFT = re.compile(rf"raw/{_PATH}+")
_AGENT = re.compile(r"collect-[a-z-]+(?::\s*)?")
_STATUS = re.compile(r"status\.md\s*(?:の)?")
_EMPTY_PARENS = re.compile(r"（\s*[、・]?\s*）")
_REPEATED = re.compile(r"([^\s（）、・。]{2,})（\1）")
_LABEL_SPACE = re.compile(r"(資料|データ|株価|短信|分析|報告書|レポート（[^）]*）) (?=[がにのを])")


def _step_name(key: str | None, number: str) -> str | None:
    return (STEP_NAMES.get(key or "") or {}).get(int(number))


def _doc_label(match: re.Match) -> str:
    stem = match.group(1).lower().strip("*-")
    return next((label for name, label in DOC_LABELS.items() if stem == name or stem.endswith(name)), "収集した資料")


def _steps(text: str, key: str | None) -> str:
    text = _LABELLED_STEP.sub(
        lambda m: f"{m.group(1)}の「{_step_name(LABEL_KEYS[m.group(1)], m.group(2)) or '確認'}」", text)
    text = _STEP_WITH_NAME.sub(r"\1", text)
    return _STEP.sub(lambda m: f"「{_step_name(key, m.group(1)) or 'この分析の確認'}」", text)


def _sources(text: str) -> str:
    text = _OUTLOOK.sub(r"地合いレポート（\1 の週）", text)
    text = _STATUS.sub("", text)
    text = _DOC.sub(_doc_label, text)
    text = _SECTION_REF.sub("", text)
    text = _DATA.sub(lambda m: DATA_LABELS.get(m.group(1), "収集したデータ"), text)
    text = _RAW_LEFT.sub("収集した資料", text)
    text = _AGENT.sub("", text)
    text = _EMPTY_PARENS.sub("", text)
    text = _REPEATED.sub(r"\1", text)
    return _LABEL_SPACE.sub(r"\1", text)


def plain(text: str | None, key: str | None = None) -> str | None:
    """text in the reader's words; key is the analysis whose 「手順N」 the text refers to (cr_status step keys)."""
    if not text or not isinstance(text, str):
        return text
    for old, new in PHRASES:
        text = text.replace(old, new)
    text = _BRIEF.sub("収集した資料", text)
    return _sources(_steps(text, key))


def plain_tree(value: object, key: str | None = None) -> object:
    """plain() over every string of a nested dict / list (a new object; the input is not changed). Name fields
    (NAME_KEYS) and dict keys are left alone: other code looks them up by value."""
    if isinstance(value, str):
        return plain(value, key)
    if isinstance(value, dict):
        return {k: v if k in NAME_KEYS else plain_tree(v, key) for k, v in value.items()}
    if isinstance(value, list):
        return [plain_tree(v, key) for v in value]
    return value


_TAGS = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.S)
_TIPS = re.compile(r'(?:title|data-tip)="([^"]*)"')


def visible_text(page: str) -> str:
    return html.unescape(_TAGS.sub(" ", page))


def leaks(page: str) -> list[str]:
    """Internal words left in the visible text of the HTML (and its hover tooltips), each with a little context;
    empty when clean. At most LEAK_LIMIT, so one build shows them all."""
    text = visible_text(page) + " " + " ".join(html.unescape(t) for t in _TIPS.findall(page))
    found = []
    for name, pattern in _INTERNAL.items():
        for m in pattern.finditer(text):
            found.append(f"{name}: …{' '.join(text[max(0, m.start() - 30):m.end() + 30].split())}…")
    return found[:LEAK_LIMIT]
