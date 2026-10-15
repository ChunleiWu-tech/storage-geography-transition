#!/usr/bin/env python3
"""Write manuscript-ready bilingual text from audited target-year results."""
from __future__ import annotations

import math
import pandas as pd

from targetyear_sensitivity_common import PAIR_ORDER
from v17t5_paths import TABLE_TARGETYEAR, TEXT_DIR


def money_million(value: float) -> str:
    return f"{value:,.2f}"


def scientific_times_ten(value: float) -> str:
    mantissa, exponent = f"{value:.2e}".split("e")
    return f"{mantissa} × 10{int(exponent)}".replace("-", "−")


def direction(value: float, *, positive: str, negative: str, zero: str) -> str:
    if value > 1e-6:
        return positive
    if value < -1e-6:
        return negative
    return zero


def main() -> None:
    pairs = pd.read_csv(TABLE_TARGETYEAR / "targetyear_pairwise_observed_minus_optimal.csv").set_index("pair_id")
    attenuation = pd.read_csv(TABLE_TARGETYEAR / "targetyear_ldes_attenuation.csv").iloc[0]
    temporal = pd.read_csv(TABLE_TARGETYEAR / "targetyear_one_hour_discretization.csv").iloc[0]
    p28 = pairs.loc["TY2028_CHRONO"]
    p33 = pairs.loc["TY2033_CHRONO"]
    p33l = pairs.loc["TY2033_CHRONO_LDES"]
    p33h = pairs.loc["TY2033_CHRONO_1H"]
    max_linkage = max(float(pairs.loc[p, "max_pair_soc_linkage_residual_mwh"]) for p in PAIR_ORDER)
    max_bound = max(float(pairs.loc[p, "max_pair_soc_bound_violation_mwh"]) for p in PAIR_ORDER)

    all_positive = all(float(pairs.loc[p, "annual_location_penalty_usd_per_yr"]) > 0 for p in PAIR_ORDER)
    sign_en = "remained positive in all four tests" if all_positive else "varied across the four tests and is reported without sign clipping"
    sign_zh = "在四组检验中均保持为正" if all_positive else "在四组检验中的符号并不完全一致，以下结果按原始符号报告"

    retention = float(attenuation["ldes_retention_fraction"])
    atten = float(attenuation["ldes_attenuation_fraction"])
    ldes_en = direction(
        atten,
        positive=f"attenuated the 2033 penalty by {atten*100:.1f}% while retaining {retention*100:.1f}%",
        negative=f"amplified the 2033 penalty by {-atten*100:.1f}% (retention {retention*100:.1f}%)",
        zero="left the 2033 penalty essentially unchanged",
    )
    ldes_zh = direction(
        atten,
        positive=f"使2033年区位惩罚降低{atten*100:.1f}%，但仍保留{retention*100:.1f}%",
        negative=f"使2033年区位惩罚增加{-atten*100:.1f}%（保留比例为{retention*100:.1f}%）",
        zero="基本未改变2033年区位惩罚",
    )
    one_hour_retention = float(temporal["one_hour_retention_fraction"])

    en = f"""# Target-year linked-chronology sensitivity: manuscript-ready text

## Results

To test whether the spatial value of inherited storage depended on independent representative-day state-of-charge cycling, we performed exact single-target-year capacity-and-dispatch re-optimizations with state of charge linked across the 12 representative months. The reconstructed-standardized minus optimized-reallocation annual cost difference {sign_en}: US${money_million(float(p28.annual_location_penalty_million_usd_per_yr))} million yr−1 in 2028 and US${money_million(float(p33.annual_location_penalty_million_usd_per_yr))} million yr−1 in 2033. These differences correspond to {100*float(p28.annual_location_penalty_fraction_of_optimized):.3f}% and {100*float(p33.annual_location_penalty_fraction_of_optimized):.3f}% of the respective optimized annual system costs. Across all eight runs, the maximum inter-month state-of-charge linkage residual was {scientific_times_ten(max_linkage)} MWh and the maximum bound violation was {scientific_times_ten(max_bound)} MWh.

A technology-specific LDES portfolio (10/24/100 h CAES; 10/24 h vanadium redox-flow batteries; 100 h hydrogen storage; and 10/24 h pumped storage) {ldes_en}. Under this sensitivity, the reconstructed-standardized minus optimized-reallocation annual cost difference was US${money_million(float(p33l.annual_location_penalty_million_usd_per_yr))} million yr−1. Pumped-storage candidates share the existing provincial resource ceiling; CAES, flow-battery and hydrogen candidates remain resource-unconstrained pressure tests, so the result is not a deployment forecast.

Refining each representative day from 4 h to an energy-preserving bounded 1 h discretization yielded a 2033 annual location penalty of US${money_million(float(p33h.annual_location_penalty_million_usd_per_yr))} million yr−1 ({one_hour_retention*100:.1f}% of the 4 h estimate). This is a temporal-discretization sensitivity reconstructed from the calibrated 4 h inputs, not observed hourly data or a full-year chronology.

## Methods scope statement

The target-year calculations are annual static re-optimizations for 2028 or 2033. They retain the inherited-storage counterfactual and linked representative-month state of charge, but do not reproduce the full multi-period transition pathway and do not constitute an 8,760-hour chronological simulation. Their annual cost differences therefore test the sign, mechanisms and LDES attenuation of the spatial effect; they are not added to, substituted for or directly equated with the frozen multi-period present-value location penalty reported in the main analysis.
"""

    zh = f"""# 目标年份跨月时序敏感性：可用于手稿的结果文本

## 结果

为检验既有储能空间价值是否由代表日之间相互独立的荷电状态循环所驱动，我们开展了目标年份容量—运行联合再优化，并将12个代表月之间的储能荷电状态严格连接。重建标准化区位相对优化重配置区位的年化成本差{sign_zh}：2028年为{money_million(float(p28.annual_location_penalty_million_usd_per_yr))}百万美元/年，2033年为{money_million(float(p33.annual_location_penalty_million_usd_per_yr))}百万美元/年，分别相当于对应优化情景年化系统成本的{100*float(p28.annual_location_penalty_fraction_of_optimized):.3f}%和{100*float(p33.annual_location_penalty_fraction_of_optimized):.3f}%。八个算例中最大月际SOC连接残差为{scientific_times_ten(max_linkage)} MWh，最大边界违反为{scientific_times_ten(max_bound)} MWh。

引入技术特异性的LDES组合（10/24/100 h压缩空气储能、10/24 h钒液流电池、100 h氢储能，以及10/24 h抽水蓄能）后，该压力测试{ldes_zh}；此时重建标准化区位相对优化区位的2033年年化成本差为{money_million(float(p33l.annual_location_penalty_million_usd_per_yr))}百万美元/年。抽水蓄能候选共享既有省域资源上限；压缩空气、液流电池和氢储能仍是未施加省域资源上限的压力测试，因此不能解释为部署预测。

把代表日由4 h细化为严格保持原分块均值且限制在物理边界内的1 h离散后，2033年区位惩罚为{money_million(float(p33h.annual_location_penalty_million_usd_per_yr))}百万美元/年，相当于4 h结果的{one_hour_retention*100:.1f}%。该检验仅衡量同一校准输入下的时间离散化影响，不代表观测小时数据或全年8760 h连续时序。

## 方法范围声明

目标年份模型分别针对2028年和2033年进行年度静态再优化，保留既有储能区位反事实并连接代表月SOC，但不重建完整的多期转型路径，也不构成8760小时连续时序模拟。因此，这些年化成本差用于检验区位效应的方向、机制及LDES削弱程度，不能与正文主模型的全期现值区位惩罚相加、替换或直接等同。
"""

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    (TEXT_DIR / "targetyear_results_EN.md").write_text(en, encoding="utf-8")
    (TEXT_DIR / "targetyear_results_ZH.md").write_text(zh, encoding="utf-8")
    print("Bilingual target-year manuscript-ready text written.")


if __name__ == "__main__":
    main()
