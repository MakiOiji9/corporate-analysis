"""The report's fixed notices in one place (docs/proposals/company-report-review-feedback.md 5.4, 決定 Q10).

The general notice (not a forecast, not a recommendation) is said twice: in 01 章's 判定の読み方 (READING) and at
the end of the report (DISCLAIMER). A table that shows prices carries the short PRICE note under it; the other
sections do not repeat it.
"""
from __future__ import annotations

READING = ("判定・点数・価格の目安は、作成日時点の材料から計算した条件の目安で、将来の株価やリターンの予想でも、"
           "売買の推奨でもない。各章では繰り返さない。")
DISCLAIMER = ("本レポートは公表資料と収集データをもとに企業分析フレームワークに沿って整理したもので、投資の勧誘・推奨ではありません。"
              "判定は作成日時点の材料による位置づけで、将来の株価を予想するものではありません。最終的な投資判断はご自身で行ってください。")
PRICE = "条件の目安。予想ではない"
