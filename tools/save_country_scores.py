#!/usr/bin/env python3
"""
국가별 Lambda-12 점수 파일 생성 (유럽 / 아시아)
정규화 기준: 같은 대륙 전체
저장: ~/everbluesea/data/wto/scores/{ISO}_lambda12_2023.json
Usage:
  python3 tools/save_country_scores.py              # 유럽 (기본)
  python3 tools/save_country_scores.py --continent asia
  python3 tools/save_country_scores.py --continent europe
"""

import argparse
import json
import os
from datetime import date

WTO_DIR  = os.path.expanduser("~/everbluesea/data/wto")
OUT_DIR  = os.path.expanduser("~/everbluesea/data/wto/scores")
YEAR     = 2023

EUROPE_REGION = {
    "FRA": "서유럽", "GBR": "서유럽", "CHE": "서유럽",
    "NLD": "서유럽", "BEL": "서유럽", "AUT": "서유럽", "DEU": "서유럽",
    "SWE": "북유럽", "NOR": "북유럽", "DNK": "북유럽", "FIN": "북유럽",
    "ITA": "남유럽", "ESP": "남유럽", "PRT": "남유럽", "GRC": "남유럽",
    "POL": "동유럽", "CZE": "동유럽", "HUN": "동유럽", "ROU": "동유럽",
    "RUS": "러시아_유라시아", "TUR": "러시아_유라시아", "UKR": "러시아_유라시아",
}

ASIA_REGION = {
    "CHN": "동아시아", "JPN": "동아시아", "KOR": "동아시아",
    "TWN": "동아시아", "HKG": "동아시아",
    "SGP": "동남아시아", "THA": "동남아시아", "VNM": "동남아시아",
    "IDN": "동남아시아", "MYS": "동남아시아", "PHL": "동남아시아",
    "IND": "남아시아",  "BGD": "남아시아",  "PAK": "남아시아",  "LKA": "남아시아",
    "SAU": "중동",      "ARE": "중동",      "ISR": "중동",      "IRN": "중동",
}

_parser = argparse.ArgumentParser()
_parser.add_argument("--continent", choices=["europe", "asia"], default="europe")
_args = _parser.parse_args()

COUNTRY_REGION = ASIA_REGION if _args.continent == "asia" else EUROPE_REGION
COUNTRIES = sorted(COUNTRY_REGION.keys())

# 원시 지표 그룹 / 코드 목록
RAW_GROUPS = {
    "trade":    ["ITS_MTV_AX", "ITS_MTV_AM", "ITS_MTP_AXVG", "ITS_MTP_AMVG"],
    "tariff":   ["TP_A_0010", "TP_A_0160", "TP_A_0430", "TP_B_0020", "TP_B_0090"],
    "services": ["ITS_CS_QAX", "ITS_CS_QAM", "BAT_BV_X", "BAT_BV_M"],
    "price":    ["ITS_MTP_AUVX", "ITS_MTP_AUVM"],
}

# Lambda-12 차원 (code, inverse, transform)
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


# ── 데이터 로드 ───────────────────────────────────────────────

def load_all() -> dict[str, dict]:
    """국가별 원시값 로드 → {iso: {code: value}}"""
    result = {}
    for iso in COUNTRIES:
        path = os.path.join(WTO_DIR, f"{iso}_{YEAR}.json")
        if not os.path.exists(path):
            print(f"  [경고] {path} 없음 — 건너뜀")
            continue
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        flat = {}
        for group, codes in RAW_GROUPS.items():
            for code in codes:
                item = raw["indicators"].get(group, {}).get(code)
                flat[code] = item["value"] if item else None
        result[iso] = flat
    return result


# ── 정규화 (22개국 전체 기준) ─────────────────────────────────

def build_norm_tables(country_data: dict) -> dict[str, dict[str, float | None]]:
    """각 지표별 전체 국가 기준 정규화 테이블 반환"""
    all_codes = [c for codes in RAW_GROUPS.values() for c in codes]
    norm = {}
    for code in all_codes:
        vals = {iso: country_data[iso].get(code) for iso in country_data}
        present = {iso: v for iso, v in vals.items() if v is not None}
        if not present:
            norm[code] = {iso: None for iso in country_data}
            continue
        lo, hi = min(present.values()), max(present.values())
        norm[code] = {}
        for iso, v in vals.items():
            if v is None:
                norm[code][iso] = None
            elif hi == lo:
                norm[code][iso] = 0.5
            else:
                norm[code][iso] = round((v - lo) / (hi - lo), 6)
    return norm


def dim_score(iso: str, indicators: list, norm: dict) -> float | None:
    """단일 국가 × 단일 차원 점수"""
    scores = []
    for code, inverse, transform in indicators:
        tbl = norm.get(code, {})
        v = tbl.get(iso)
        if v is None:
            continue
        if transform == "abs":
            # abs transform: 원시값 절댓값 → 이미 norm 테이블에 없으므로 직접 계산
            pass  # abs norm은 별도 테이블에서 처리됨
        scores.append(1.0 - v if inverse else v)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def build_abs_norm(country_data: dict, code: str) -> dict[str, float | None]:
    """절댓값 기반 정규화 테이블"""
    vals = {iso: abs(country_data[iso][code]) if country_data[iso].get(code) is not None else None
            for iso in country_data}
    present = {iso: v for iso, v in vals.items() if v is not None}
    if not present:
        return {iso: None for iso in country_data}
    lo, hi = min(present.values()), max(present.values())
    out = {}
    for iso, v in vals.items():
        if v is None:
            out[iso] = None
        elif hi == lo:
            out[iso] = 0.5
        else:
            out[iso] = round((v - lo) / (hi - lo), 6)
    return out


def compute_lambda12(iso: str, country_data: dict, norm: dict, abs_norms: dict) -> dict:
    dim_scores = {}
    for dim, (name, indicators) in DIMENSIONS.items():
        if not indicators:
            dim_scores[dim] = None
            continue
        scores = []
        for code, inverse, transform in indicators:
            if transform == "abs":
                v = abs_norms.get(code, {}).get(iso)
            else:
                v = norm.get(code, {}).get(iso)
            if v is None:
                continue
            scores.append(1.0 - v if inverse else v)
        dim_scores[dim] = round(sum(scores) / len(scores), 4) if scores else None
    return dim_scores


def compute_eta(dim_scores: dict) -> float | None:
    vals = [v for dim, v in dim_scores.items() if dim != "A7" and v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


# ── 메인 ─────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"로딩 중...")
    country_data = load_all()
    available = list(country_data.keys())
    print(f"  {len(available)}개국 로드 완료: {', '.join(sorted(available))}\n")

    # 정규화 테이블 구축
    norm = build_norm_tables(country_data)
    abs_norms = {
        code: build_abs_norm(country_data, code)
        for group in RAW_GROUPS.values()
        for code in group
    }

    results = {}
    for iso in sorted(available):
        raw_vals = country_data[iso]
        dim_scores = compute_lambda12(iso, country_data, norm, abs_norms)
        eta = compute_eta(dim_scores)

        output = {
            "country": iso,
            "year":    YEAR,
            "region":  COUNTRY_REGION.get(iso, "기타"),
            "updated": date.today().isoformat(),
            "wto_raw": {
                code: raw_vals.get(code)
                for group in RAW_GROUPS.values()
                for code in group
            },
            "lambda12": {
                dim: {
                    "name":  DIMENSIONS[dim][0],
                    "score": dim_scores[dim],
                }
                for dim in DIMENSIONS
            },
            "eta": eta,
        }

        out_path = os.path.join(OUT_DIR, f"{iso}_lambda12_{YEAR}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        results[iso] = eta
        print(f"  {iso:4s}  η={eta:.4f}  ({COUNTRY_REGION.get(iso,'기타')})  → {os.path.basename(out_path)}")

    # 전체 순위 출력
    print(f"\n{'─'*45}")
    print(f"  유럽 {len(available)}개국 η 순위 (정규화 기준: 전체)")
    print(f"{'─'*45}")
    for rank, (iso, eta) in enumerate(sorted(results.items(), key=lambda x: -(x[1] or 0)), 1):
        region = COUNTRY_REGION.get(iso, "기타")
        print(f"  {rank:2d}. {iso}  {eta:.4f}  [{region}]")

    print(f"\n저장 완료: {OUT_DIR}")
    print(f"파일 수: {len(available)}개\n")


if __name__ == "__main__":
    main()
