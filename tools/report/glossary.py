"""Plain-language explanations for the beginner slide and the glossary (no judgement, no advice).

TERMS: term -> one-line explanation. The glossary slide lists only the terms that appear in this
week's outlook.md, so a term is matched by the words in ALIASES as well.
JUDGEMENTS: what each of the four judgement words means, in everyday words.
"""
from __future__ import annotations

import re

TERMS: dict[str, str] = {
    "政策金利": "中央銀行（日本は日銀、米国は FRB）が決める短期の金利。上げると借入が高くなり、景気と物価を冷ます",
    "利上げ": "政策金利を引き上げること。物価の上がりすぎを抑えるために行う",
    "FOMC": "米国の金融政策を決める会合（年8回）。政策金利をここで決める",
    "日銀会合": "日本銀行の金融政策決定会合（年8回）。政策金利をここで決める",
    "実質金利": "金利から物価の上昇率を引いたもの。マイナスなら、お金を借りやすい（緩和的な）状態",
    "長期金利": "10年国債の利回り。住宅ローンや企業の借入の金利の目安になる",
    "長短金利差": "長期金利と短期金利の差。小さい（またはマイナス）ほど、景気の先行きへの警戒が強いとされる",
    "ブレークイーブン": "市場が予想している今後10年の物価上昇率（国債の価格から計算する）",
    "益利回り": "株価に対する企業の利益の割合（PER の逆数）。国債の利回りより高いほど、株を持つ見返りが大きい",
    "予想PER": "株価が予想利益の何倍かを表す数値。高いほど割高とされる",
    "HY スプレッド": "信用力の低い企業の社債の利回りと国債の利回りの差。広がるのは、お金を貸す側が警戒しているしるし",
    "IG スプレッド": "信用力の高い企業の社債の利回りと国債の利回りの差。HY スプレッドより動きが小さい",
    "VIX": "米国株の値動きの大きさの予想を表す指数。「恐怖指数」とも呼ばれ、高いほど市場が不安定",
    "移動平均": "一定期間の株価の平均。200日移動平均は、長めの流れの目安",
    "CPI": "消費者物価指数。身の回りのモノやサービスの値段の動きを表す",
    "コアPCE": "米国の物価の指標の一つ。食品とエネルギーを除いた個人消費の物価で、FRB が重視する",
    "雇用統計": "米国で毎月公表される雇用の統計。雇用者数と失業率が景気の強さの目安になる",
    "短観": "日銀が四半期ごとに企業に景気の感じ方を聞く調査",
    "景気動向指数": "生産・雇用などの統計をまとめて景気の動きを表す指数。一致指数は今の景気、先行指数は先行きの目安",
    "海外投資家": "日本株を売買する海外の投資家。日本株の売買の大きな割合を占める",
    "CFTC": "米国の先物取引の監督機関。投機筋が株価指数先物を買い越しているか売り越しているかを毎週公表する",
    "WTI": "米国の代表的な原油価格。ガソリンや電気代など、物価に広く影響する",
    "ドル指数": "主要な通貨に対するドルの強さを表す指数",
    "実質実効為替レート": "物価の違いを調整した円の総合的な強さ。低いほど円の購買力が弱い",
    "暫定予算": "米国で本予算が成立しないとき、政府の支出を一時的に続けるための予算。期限までに延長できないと政府機関が一部止まる",
}

ALIASES: dict[str, tuple[str, ...]] = {
    "HY スプレッド": ("HYスプレッド", "ハイイールド"),
    "IG スプレッド": ("IGスプレッド", "投資適格社債スプレッド"),
    "実質金利": ("実質政策金利", "実質10年"),
    "ブレークイーブン": ("BEI",),
    "日銀会合": ("日銀 金融政策決定会合", "金融政策決定会合"),
    "暫定予算": ("暫定歳出法", "CR"),
    "移動平均": ("200日線", "50日線"),
}

JUDGEMENTS: dict[str, str] = {
    "強気": "株価を押し上げる材料が多く、下げにつながる材料が少ない局面",
    "中立": "押し上げる材料と下げにつながる材料が釣り合っている局面",
    "慎重": "下げにつながる材料のほうが多く、値動きに注意が要る局面",
    "弱気": "株価の下落と、ほかの下げにつながる材料が重なっている局面",
}


def _appears(word: str, text: str) -> bool:
    """Plain substring for Japanese; an ASCII word must stand alone ('CR' is not found in 'CRE')."""
    if word.isascii():
        return re.search(rf"(?<![A-Za-z]){re.escape(word)}(?![A-Za-z])", text) is not None
    return word in text


def terms_in(text: str) -> list[tuple[str, str]]:
    """(term, explanation) for every term (or alias) that appears in text, in TERMS order."""
    return [(term, desc) for term, desc in TERMS.items()
            if _appears(term, text) or any(_appears(a, text) for a in ALIASES.get(term, ()))]


def jargon_in(text: str) -> list[str]:
    """Terms a beginner summary should not use (the glossary terms except the everyday ones)."""
    everyday = {"政策金利", "利上げ", "長期金利", "海外投資家", "雇用統計", "FOMC", "日銀会合"}
    return [term for term, _ in terms_in(text) if term not in everyday]
