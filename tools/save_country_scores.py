#!/usr/bin/env python3
"""
국가별 Λ¹²(Lambda-12) η 점수 산출 — UN 193개국 모천 버전
============================================================
정규화 기준: 전체 193개국 (방식 A — 권역 간 비교 가능)
입력: ~/-everbluesea/data/wto/{ISO}_2023.json
출력: ~/-everbluesea/data/wto/scores/{ISO}_lambda12_2023.json
명단: scripts/un193_codes.json (193개국 + 7권역)

12변수(A1~A12) 심장부는 기존(노트북 70개국) 버전을 그대로 계승.
경로·명단·권역·정규화 범위만 새 환경(193개국)에 맞게 확장.

Usage:
  python tools/save_country_scores.py                 # 전체(global) η
  python tools/save_country_scores.py --region 유럽    # 특정 권역만 표시
                                                       # (정규화는 항상 전체 기준)
"""

import argparse
import json
import os
from datetime import date

# ── 경로 (새 환경: 하이픈 폴더) ───────────────────────────────
BASE_DIR  = os.path.expanduser("~/-everbluesea")
WTO_DIR   = os.path.join(BASE_DIR, "data", "wto")
OUT_DIR   = os.path.join(BASE_DIR, "data", "wto", "scores")
CODES_PATH = os.path.join(BASE_DIR, "scripts", "un193_codes.json")
YEAR      = 2023

# ── 원시 지표 그룹 / 코드 (계승) ──────────────────────────────
RAW_GROUPS = {
    "trade":    ["ITS_MTV_AX", "ITS_MTV_AM", "ITS_MTP_AXVG", "ITS_MTP_AMVG"],
    "tariff":   ["TP_A_0010", "TP_A_0160", "TP_A_0430", "TP_B_0020", "TP_B_0090"],
    "services": ["ITS_CS_QAX", "ITS_CS_QAM", "BAT_BV_X", "BAT_BV_M"],
    "price":    ["ITS_MTP_AUVX", "ITS_MTP_AUVM"],
}

# ── Λ¹² 12차원 (code, inverse, transform) — 계승, 손대지 않음 ──
DIMENSIONS = {
    "A1":  ("수출력",   [("ITS_MTV_AX",   False, None), ("ITS_MTP_AXVG", False, None)]),
    "A2":  ("제도신뢰", [("TP_B_0020",    False, None), ("TP_A_0010",    True,  None)]),
    "A3":  ("사회결속", [("ITS_CS_QAX",   False, None), ("ITS_CS_QAM",   False, None)]),
    "A4":  ("경제역량", [("ITS_MTV_AX",   False, None), ("ITS_MTV_AM",   False, None),
                        ("ITS_MTP_AXVG", False, None), ("ITS_MTP_AMVG", False, None)]),
    "A5":  ("지속영속", [("ITS_MTP_AUVX", False, None), ("ITS_MTP_AUVM", False, None)]),
    "A6":  ("환경지속", [("TP_A_0160",    True,  None), ("TP_A_0430",    False, None)]),
    "A7":  ("인구동태", []),
    "A8":  ("거버넌스", [("TP_A_0010",    True,  None), ("TP_B_0090",    False, None)]),
    "A9":  ("지정학",   [("ITS_MTP_AXVG", False, "abs"), ("ITS_MTP_AMVG", False, "abs")]),
    "A10": ("문화정체", [("ITS_CS_QAX",   False, None)]),
    "A11": ("에너지",   [("ITS_MTV_AM",   False, None), ("ITS_MTP_AMVG", False, None)]),
    "A12": ("이동성",   [("ITS_CS_QAX",   False, None), ("ITS_CS_QAM",   False, None),
                        ("BAT_BV_X",     False, None), ("BAT_BV_M",     False, None)]),
}


# ── EU 27개 회원국 (2023 기준, 위키 확인) ────────────────────
# 영국(GBR)은 2020 브렉시트로 제외 — 2023엔 자국 관세 보유(15/15).
# 이들은 EU 공동관세를 동일하게 적용받아 개별 관세 통계가 없음.
EU27 = {
    "DEU", "FRA", "ITA", "NLD", "BEL", "LUX",          # 창립 6국
    "DNK", "IRL", "GRC", "ESP", "PRT",                  # ~1986
    "SWE", "AUT", "FIN",                                # 1995
    "LVA", "LTU", "MLT", "SVK", "SVN", "EST",           # 2004
    "CZE", "CYP", "POL", "HUN",                         # 2004
    "ROU", "BGR",                                       # 2007
    "HRV",                                              # 2013
}

# EU 공동관세를 채울 관세 지표 (tariff 그룹)
TARIFF_CODES = ["TP_A_0010", "TP_A_0160", "TP_A_0430", "TP_B_0020", "TP_B_0090"]


def load_eu_common_tariff() -> dict[str, float | None]:
    """EU_2023.json에서 공동관세(tariff) 5개 값을 읽어 반환.
    없으면 빈 dict (보정 비활성)."""
    eu_path = os.path.join(WTO_DIR, "EU_2023.json")
    if not os.path.exists(eu_path):
        return {}
    with open(eu_path, encoding="utf-8") as f:
        raw = json.load(f)
    out = {}
    tariff = raw.get("indicators", {}).get("tariff", {})
    for code in TARIFF_CODES:
        item = tariff.get(code)
        out[code] = item["value"] if item and item.get("value") is not None else None
    return out


# ── 명단 로드: un193_codes.json → {iso: region} ──────────────
def load_country_region() -> dict[str, str]:
    with open(CODES_PATH, encoding="utf-8") as f:
        codes = json.load(f)
    return {v["iso3"]: v["region"] for v in codes.values()}


# ── 데이터 로드: 폴더 전체 스캔 (있는 파일만) ─────────────────
def load_all(country_region: dict[str, str],
             eu_adjust: bool = False,
             eu_tariff: dict | None = None) -> tuple[dict, set]:
    """data/wto 폴더에 실제 존재하는 모든 {ISO}_2023.json 로드.
    eu_adjust=True면 EU27 회원국의 관세 결측을 EU 공동관세로 채움.
    반환: (country_data, 보정된 국가 집합)"""
    result = {}
    adjusted = set()
    eu_tariff = eu_tariff or {}
    for iso in sorted(country_region.keys()):
        path = os.path.join(WTO_DIR, f"{iso}_{YEAR}.json")
        if not os.path.exists(path):
            continue  # 수집 안 된 국가는 조용히 건너뜀 (명단엔 남음)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        flat = {}
        for group, codes in RAW_GROUPS.items():
            for code in codes:
                item = raw.get("indicators", {}).get(group, {}).get(code)
                flat[code] = item["value"] if item and item.get("value") is not None else None

        # ── EU 보정: EU27 회원국의 관세 결측을 공동관세로 채움 ──
        if eu_adjust and iso in EU27 and eu_tariff:
            filled = False
            for code in TARIFF_CODES:
                if flat.get(code) is None and eu_tariff.get(code) is not None:
                    flat[code] = eu_tariff[code]
                    filled = True
            if filled:
                adjusted.add(iso)

        flat["_collected"] = raw.get("collected", sum(1 for k, v in flat.items()
                                                       if k != "_collected" and v is not None))
        result[iso] = flat
    return result, adjusted


# ── 정규화 (전체 193개국 기준) — 계승 ─────────────────────────
def build_norm_tables(country_data: dict) -> dict[str, dict]:
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


def build_abs_norm(country_data: dict, code: str) -> dict[str, float | None]:
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


# ── 12차원 점수 + η — 계승 ────────────────────────────────────
def compute_lambda12(iso: str, norm: dict, abs_norms: dict) -> dict:
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


# ── 메인 ──────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=None,
                        help="특정 권역만 순위 표시 (정규화는 항상 전체 기준)")
    parser.add_argument("--eu-adjust", action="store_true",
                        help="EU27 회원국의 관세 결측을 EU 공동관세로 보정")
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    country_region = load_country_region()

    # EU 보정 준비
    eu_tariff = {}
    if args.eu_adjust:
        eu_tariff = load_eu_common_tariff()
        if eu_tariff:
            vals = ", ".join(f"{k}={v}" for k, v in eu_tariff.items() if v is not None)
            print(f"[EU 보정 ON] 공동관세 적용: {vals}")
        else:
            print("[경고] EU_2023.json 없음 — 보정 불가, 날것으로 진행")

    mode = "EU보정" if (args.eu_adjust and eu_tariff) else "날것"
    print(f"로딩 중... (전체 193개국 기준 정규화 · {mode})")
    country_data, adjusted = load_all(country_region, args.eu_adjust, eu_tariff)
    available = sorted(country_data.keys())
    print(f"  데이터 보유: {len(available)}개국 / 명단 {len(country_region)}개국")
    if adjusted:
        print(f"  EU 보정 적용: {len(adjusted)}개국 ({', '.join(sorted(adjusted))})")
    print()

    # 전체 기준 정규화
    norm = build_norm_tables(country_data)
    abs_norms = {
        code: build_abs_norm(country_data, code)
        for group in RAW_GROUPS.values()
        for code in group
    }

    # 보정 모드면 별도 폴더(scores_eu)에 저장 — 날것과 분리
    out_dir = OUT_DIR + "_eu" if (args.eu_adjust and eu_tariff) else OUT_DIR
    os.makedirs(out_dir, exist_ok=True)

    # 산출
    results = {}       # iso -> eta (None 포함)
    collected = {}     # iso -> 수집 지표 수
    for iso in available:
        dim_scores = compute_lambda12(iso, norm, abs_norms)
        eta = compute_eta(dim_scores)
        results[iso] = eta
        collected[iso] = country_data[iso].get("_collected", 0)

        output = {
            "country": iso,
            "year":    YEAR,
            "region":  country_region.get(iso, "미분류"),
            "collected": collected[iso],
            "eu_adjusted": iso in adjusted,
            "updated": date.today().isoformat(),
            "wto_raw": {
                code: country_data[iso].get(code)
                for group in RAW_GROUPS.values()
                for code in group
            },
            "lambda12": {
                dim: {"name": DIMENSIONS[dim][0], "score": dim_scores[dim]}
                for dim in DIMENSIONS
            },
            "eta": eta,
        }
        out_path = os.path.join(out_dir, f"{iso}_lambda12_{YEAR}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    # η 산출국 / 데이터없음(사각지대) 분리
    scored   = {iso: e for iso, e in results.items() if e is not None}
    no_data  = [iso for iso, e in results.items() if e is None]

    # ── 전체 η 순위 ──
    bar = "=" * 60
    print(bar)
    print(f"  Global η 순위 — {len(scored)}개국 (전체 193개국 기준 · {mode})")
    print(bar)
    for rank, (iso, eta) in enumerate(sorted(scored.items(), key=lambda x: -x[1]), 1):
        region = country_region.get(iso, "미분류")
        star = " ★" if iso == "KOR" else ""
        print(f"  {rank:3d}. {iso}  η={eta:.4f}  [{region}]  ({collected[iso]}/15){star}")

    # ── 권역별 평균 η ──
    print("\n" + bar)
    print("  권역별 평균 η (η 산출국 기준)")
    print(bar)
    region_etas: dict[str, list] = {}
    for iso, eta in scored.items():
        region_etas.setdefault(country_region.get(iso, "미분류"), []).append(eta)
    region_avg = {r: sum(v) / len(v) for r, v in region_etas.items()}
    for rank, (region, avg) in enumerate(sorted(region_avg.items(), key=lambda x: -x[1]), 1):
        n = len(region_etas[region])
        print(f"  {rank}. {region:18s}  평균 η={avg:.4f}  ({n}개국)")

    # ── 특정 권역 상세 (옵션) ──
    if args.region:
        print("\n" + bar)
        print(f"  [{args.region}] 권역 내 순위")
        print(bar)
        sub = {iso: e for iso, e in scored.items()
               if country_region.get(iso) == args.region}
        if not sub:
            print(f"  (해당 권역 η 산출국 없음 — 권역명 확인: {sorted(set(country_region.values()))})")
        else:
            for rank, (iso, eta) in enumerate(sorted(sub.items(), key=lambda x: -x[1]), 1):
                print(f"  {rank:2d}. {iso}  η={eta:.4f}  ({collected[iso]}/15)")

    # ── 데이터 사각지대 (η 산출불가) ──
    print("\n" + bar)
    print(f"  데이터 사각지대 — η 산출불가 {len(no_data)}개국 (보간 없음, 명단 유지)")
    print(bar)
    if no_data:
        for iso in sorted(no_data):
            print(f"  {iso}  [{country_region.get(iso, '미분류')}]  ({collected[iso]}/15) — 별도 경로 필요")
    else:
        print("  (없음)")

    # ── 미수집 (명단엔 있으나 파일 없음) ──
    not_collected = sorted(set(country_region.keys()) - set(available))
    if not_collected:
        print("\n" + bar)
        print(f"  미수집 — 파일 없음 {len(not_collected)}개국")
        print(bar)
        print(f"  {', '.join(not_collected)}")

    print(f"\n저장 완료: {out_dir}")
    print(f"  η 산출 {len(scored)} / 사각지대 {len(no_data)} / 미수집 {len(not_collected)}")
    if args.eu_adjust and eu_tariff:
        print(f"  EU 보정 {len(adjusted)}개국 적용 (날것과 별도 폴더 scores_eu에 저장)")


if __name__ == "__main__":
    main()
