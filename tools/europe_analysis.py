#!/usr/bin/env python3
"""
유럽 권역별 WTO 비교표 + Lambda-12 점수 일괄 생성
Usage: python3 tools/europe_analysis.py
"""

import json
import os
from datetime import date

BASE     = os.path.expanduser("~/everbluesea/data/wto")
YEAR     = 2023

REGIONS = {
    "서유럽":       ["FRA", "GBR", "CHE", "NLD", "BEL", "AUT"],
    "북유럽":       ["SWE", "NOR", "DNK", "FIN"],
    "남유럽":       ["ITA", "ESP", "PRT", "GRC"],
    "동유럽":       ["POL", "CZE", "HUN", "ROU"],
    "러시아_유라시아": ["RUS", "TUR", "UKR"],
}

# Lambda-12 차원 정의 (indicator, inverse, transform)
DIMENSIONS = {
    "A1":  ("인프라",    [("ITS_MTV_AX",   False, None), ("ITS_MTP_AXVG", False, None)]),
    "A2":  ("제도신뢰",  [("TP_B_0020",    False, None), ("TP_A_0010",    True,  None)]),
    "A3":  ("사회결속",  [("ITS_CS_QAX",   False, None), ("ITS_CS_QAM",   False, None)]),
    "A4":  ("경제역량",  [("ITS_MTV_AX",   False, None), ("ITS_MTV_AM",   False, None),
                          ("ITS_MTP_AXVG", False, None), ("ITS_MTP_AMVG", False, None)]),
    "A5":  ("지식혁신",  [("ITS_MTP_AUVX", False, None), ("ITS_MTP_AUVM", False, None)]),
    "A6":  ("환경지속",  [("TP_A_0160",    True,  None), ("TP_A_0430",    False, None)]),
    "A7":  ("인구동태",  []),
    "A8":  ("거버넌스",  [("TP_A_0010",    True,  None), ("TP_B_0090",    False, None)]),
    "A9":  ("지정학",    [("ITS_MTP_AXVG", False, "abs"), ("ITS_MTP_AMVG", False, "abs")]),
    "A10": ("문화정체",  [("ITS_CS_QAX",   False, None)]),
    "A11": ("에너지",    [("ITS_MTV_AM",   False, None), ("ITS_MTP_AMVG", False, None)]),
    "A12": ("이동성",    [("ITS_CS_QAX",   False, None), ("ITS_CS_QAM",   False, None),
                          ("BAT_BV_X",     False, None), ("BAT_BV_M",     False, None)]),
}

# 지표 레이블
INDICATOR_LABELS = {
    "ITS_MTV_AX":   "상품수출 (백만$)",
    "ITS_MTV_AM":   "상품수입 (백만$)",
    "ITS_MTP_AXVG": "수출물량증가율 (%)",
    "ITS_MTP_AMVG": "수입물량증가율 (%)",
    "TP_A_0010":    "MFN 단순평균관세 (%)",
    "TP_A_0160":    "MFN 가중평균관세 (%)",
    "TP_A_0430":    "무관세 품목 비율 (%)",
    "TP_B_0020":    "양허관세 커버리지 (%)",
    "TP_B_0090":    "바운드 단순평균 (%)",
    "ITS_CS_QAX":   "서비스수출 (백만$)",
    "ITS_CS_QAM":   "서비스수입 (백만$)",
    "BAT_BV_X":     "서비스수지 크레딧 (백만$)",
    "BAT_BV_M":     "서비스수지 데빗 (백만$)",
    "ITS_MTP_AUVX": "수출단가지수 (2015=100)",
    "ITS_MTP_AUVM": "수입단가지수 (2015=100)",
}

GROUP_ORDER = ["trade", "tariff", "services", "price"]
GROUP_CODES = {
    "trade":    ["ITS_MTV_AX", "ITS_MTV_AM", "ITS_MTP_AXVG", "ITS_MTP_AMVG"],
    "tariff":   ["TP_A_0010", "TP_A_0160", "TP_A_0430", "TP_B_0020", "TP_B_0090"],
    "services": ["ITS_CS_QAX", "ITS_CS_QAM", "BAT_BV_X", "BAT_BV_M"],
    "price":    ["ITS_MTP_AUVX", "ITS_MTP_AUVM"],
}


# ── 데이터 로드 ──────────────────────────────────────────────

def load_country(iso: str) -> dict | None:
    path = os.path.join(BASE, f"{iso}_{YEAR}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def get_val(data: dict, group: str, code: str) -> float | None:
    item = data["indicators"].get(group, {}).get(code)
    return item["value"] if item else None


# ── comparison JSON ──────────────────────────────────────────

def make_comparison(region_name: str, countries: list[str]) -> dict:
    loaded = {c: load_country(c) for c in countries}
    available = [c for c in countries if loaded[c]]

    data_block = {}
    for group in GROUP_ORDER:
        data_block[group] = {}
        for code in GROUP_CODES[group]:
            data_block[group][code] = {
                "label": INDICATOR_LABELS[code],
                "values": {
                    c: get_val(loaded[c], group, code) if loaded[c] else None
                    for c in available
                }
            }
    return {
        "title":    f"WTO {region_name} 비교",
        "region":   region_name,
        "year":     YEAR,
        "updated":  date.today().isoformat(),
        "countries": available,
        "data":     data_block,
    }


# ── Lambda-12 ────────────────────────────────────────────────

def normalize(vals: dict, inverse: bool) -> dict:
    present = {c: v for c, v in vals.items() if v is not None}
    if not present:
        return {c: None for c in vals}
    lo, hi = min(present.values()), max(present.values())
    if hi == lo:
        return {c: (0.5 if v is not None else None) for c, v in vals.items()}
    out = {}
    for c, v in vals.items():
        if v is None:
            out[c] = None
        else:
            s = (v - lo) / (hi - lo)
            out[c] = round(1.0 - s if inverse else s, 4)
    return out

def score_dimension(indicators: list, flat: dict, countries: list) -> dict:
    if not indicators:
        return {c: None for c in countries}
    layers = []
    for code, inverse, transform in indicators:
        raw = {c: flat.get(code, {}).get(c) for c in countries}
        if transform == "abs":
            raw = {c: abs(v) if v is not None else None for c, v in raw.items()}
        layers.append(normalize(raw, inverse))
    result = {}
    for c in countries:
        vals = [l[c] for l in layers if l[c] is not None]
        result[c] = round(sum(vals) / len(vals), 4) if vals else None
    return result

def make_lambda12(comparison: dict) -> dict:
    countries = comparison["countries"]
    flat = {
        code: item["values"]
        for group in comparison["data"].values()
        for code, item in group.items()
    }
    dim_scores = {
        dim: score_dimension(indics, flat, countries)
        for dim, (_, indics) in DIMENSIONS.items()
    }
    eta = {}
    for c in countries:
        vals = [dim_scores[d][c] for d in DIMENSIONS
                if d != "A7" and dim_scores[d][c] is not None]
        eta[c] = round(sum(vals) / len(vals), 4) if vals else None

    return {
        "region":   comparison["region"],
        "year":     YEAR,
        "updated":  date.today().isoformat(),
        "countries": countries,
        "dimensions": {
            dim: {"name": DIMENSIONS[dim][0], "scores": dim_scores[dim]}
            for dim in DIMENSIONS
        },
        "eta": eta,
    }


# ── 출력 ─────────────────────────────────────────────────────

def print_comparison(comp: dict) -> None:
    countries = comp["countries"]
    col = 12
    print(f"\n{'─'*60}")
    print(f"  {comp['title']} ({comp['year']})")
    print(f"{'─'*60}")
    header = f"  {'지표':<30}" + "".join(f"{c:>{col}}" for c in countries)
    print(header)
    print(f"  {'─'*(30 + col*len(countries))}")
    for group in GROUP_ORDER:
        group_label = {"trade":"【무역】","tariff":"【관세】","services":"【서비스】","price":"【가격】"}[group]
        print(f"\n  {group_label}")
        for code, item in comp["data"][group].items():
            vals = "".join(
                f"{'—':>{col}}" if item["values"].get(c) is None
                else f"{item['values'][c]:>{col},.1f}"
                for c in countries
            )
            print(f"  {item['label']:<30}{vals}")

def print_lambda12(scores: dict) -> None:
    countries = scores["countries"]
    col = 9
    print(f"\n{'─'*60}")
    print(f"  Lambda-12 — {scores['region']} ({scores['year']})")
    print(f"{'─'*60}")
    header = f"  {'':14}" + "".join(f"{c:>{col}}" for c in countries)
    print(header)
    print(f"  {'─'*(14 + col*len(countries))}")
    for dim, info in scores["dimensions"].items():
        label = f"{dim}({info['name']})"
        row = "".join(
            f"{'—':>{col}}" if info["scores"].get(c) is None
            else f"{info['scores'][c]:>{col}.4f}"
            for c in countries
        )
        print(f"  {label:<14}{row}")
    print(f"  {'─'*(14 + col*len(countries))}")
    eta_row = "".join(
        f"{'—':>{col}}" if scores["eta"].get(c) is None
        else f"{scores['eta'][c]:>{col}.4f}"
        for c in countries
    )
    print(f"  {'η (평균)':<14}{eta_row}")


# ── 메인 ─────────────────────────────────────────────────────

def main() -> None:
    all_eta = {}

    for region_name, countries in REGIONS.items():
        comp   = make_comparison(region_name, countries)
        scores = make_lambda12(comp)

        # 저장
        slug = region_name.replace("/", "_").replace(" ", "_")
        comp_path   = os.path.join(BASE, f"comparison_{slug}_{YEAR}.json")
        scores_path = os.path.join(BASE, f"lambda12_{slug}_{YEAR}.json")
        with open(comp_path,   "w", encoding="utf-8") as f:
            json.dump(comp,   f, ensure_ascii=False, indent=2)
        with open(scores_path, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)

        print_comparison(comp)
        print_lambda12(scores)

        for c, v in scores["eta"].items():
            all_eta[c] = v

    # 권역별 η 종합 요약
    print(f"\n\n{'═'*60}")
    print(f"  유럽 권역별 η 종합 순위 ({YEAR})")
    print(f"{'═'*60}")
    for region_name, countries in REGIONS.items():
        comp = json.load(open(os.path.join(BASE, f"comparison_{region_name.replace('/','_').replace(' ','_')}_{YEAR}.json")))
        scores = json.load(open(os.path.join(BASE, f"lambda12_{region_name.replace('/','_').replace(' ','_')}_{YEAR}.json")))
        print(f"\n  [{region_name}]")
        ranked = sorted(
            [(c, scores["eta"].get(c)) for c in scores["countries"] if scores["eta"].get(c) is not None],
            key=lambda x: -x[1]
        )
        for rank, (c, val) in enumerate(ranked, 1):
            print(f"    {rank}. {c}  η={val:.4f}")

    print()

if __name__ == "__main__":
    main()
