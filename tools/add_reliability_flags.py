#!/usr/bin/env python3
"""
각 국가 Lambda-12 scores JSON에 신뢰도 플래그 추가
flags: outlier_flag, missing_dims, missing_reason, special_flag, reliability
Usage: python3 tools/add_reliability_flags.py
"""

import json
import os

SCORES_DIR = os.path.expanduser("~/everbluesea/data/wto/scores")
YEAR = 2023

# A9(지정학) 극단값 임계치 — 68개국 정규화 기준 0.85 초과
A9_OUTLIER_THRESHOLD = 0.85

# UN 최빈국(LDC) 목록 — 2023년 기준 우리 데이터셋 내 해당 국가
# 특혜관세(EBA·AGOA 등)로 A2·A6·A8이 실제 제도 수준보다 높게 산출됨
LDC = {"BGD", "ETH", "MOZ", "UGA", "TZA", "ZMB", "COD", "SEN"}

# EU 회원국 — 개별 관세 데이터 없음(공동관세체계 WTO 보고 구조)
# A2·A6·A8 결측은 제도 문제가 아닌 보고 구조상 필연
EU_MEMBERS = {
    "FRA", "DEU", "ITA", "ESP", "NLD", "BEL", "AUT",
    "SWE", "FIN", "DNK", "POL", "CZE", "HUN", "ROU", "PRT", "GRC",
}

SCORED_DIMS = [f"A{i}" for i in range(1, 13) if i != 7]  # A7 제외


def missing_reason(iso: str, missing_count: int) -> str:
    if iso in EU_MEMBERS and missing_count > 0:
        return "EU공동관세"
    if missing_count > 0:
        return "미신고"
    return ""


def calc_reliability(iso: str, outlier: bool, missing: int, special: bool) -> str:
    reason = missing_reason(iso, missing)
    is_eu_structural = (reason == "EU공동관세")

    if outlier:
        return "하"
    if not is_eu_structural and missing >= 3:
        return "하"
    if special and outlier:          # 이미 처리됐지만 명시
        return "하"
    if missing >= 1 or special:
        return "중"
    return "상"


def process_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    iso = data["country"]
    dim_scores = data["lambda12"]

    # A9 점수
    a9_score = dim_scores.get("A9", {}).get("score")
    outlier_flag = bool(a9_score is not None and a9_score > A9_OUTLIER_THRESHOLD)

    # 결측 차원 수 (A7 제외)
    missing_dims = sum(
        1 for d in SCORED_DIMS
        if dim_scores.get(d, {}).get("score") is None
    )

    # 최빈국 특혜관세 플래그
    special_flag = iso in LDC

    # 신뢰도
    reliability = calc_reliability(iso, outlier_flag, missing_dims, special_flag)

    data["flags"] = {
        "outlier_flag":   outlier_flag,
        "a9_score":       round(a9_score, 4) if a9_score is not None else None,
        "missing_dims":   missing_dims,
        "missing_reason": missing_reason(iso, missing_dims),
        "special_flag":   special_flag,
        "reliability":    reliability,
    }

    return data


def main() -> None:
    files = sorted(f for f in os.listdir(SCORES_DIR)
                   if f.endswith(f"_lambda12_{YEAR}.json"))

    counts = {"상": 0, "중": 0, "하": 0}
    flagged = {"outlier": [], "special": [], "missing_high": [], "eu": []}

    print(f"{'국가':<6} {'η':>6}  {'outlier':>7}  {'missing':>7}  {'special':>7}  {'reason':<14}  reliability")
    print("─" * 80)

    for fname in files:
        path = os.path.join(SCORES_DIR, fname)
        data = process_file(path)
        f = data["flags"]
        iso = data["country"]

        print(f"  {iso:<4}  {data['eta']:>6.4f}  "
              f"{'✓' if f['outlier_flag'] else '':>7}  "
              f"{f['missing_dims']:>7}  "
              f"{'✓' if f['special_flag'] else '':>7}  "
              f"{f['missing_reason']:<14}  "
              f"{f['reliability']}")

        counts[f["reliability"]] += 1
        if f["outlier_flag"]:     flagged["outlier"].append(iso)
        if f["special_flag"]:     flagged["special"].append(iso)
        if f["missing_dims"] >= 3 and iso not in EU_MEMBERS:
            flagged["missing_high"].append(iso)
        if iso in EU_MEMBERS:     flagged["eu"].append(iso)

        with open(path, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)

    print("─" * 80)
    print(f"\n  신뢰도 분포: 상={counts['상']}  중={counts['중']}  하={counts['하']}")
    print(f"  outlier_flag  : {', '.join(flagged['outlier'])}")
    print(f"  special_flag  : {', '.join(flagged['special'])}")
    print(f"  missing ≥3    : {', '.join(flagged['missing_high']) or '없음'}")
    print(f"  EU구조 결측   : {len(flagged['eu'])}개국\n")


if __name__ == "__main__":
    main()
