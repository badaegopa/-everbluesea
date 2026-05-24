#!/usr/bin/env python3
"""
fetch_worldbank.py — Λ¹² 국가편 World Bank 데이터 수집 모듈
무인증 / 무제한 / WGI source=75 포함
fetch_lambda12.py에서 import하여 사용

사용법:
  from fetch_worldbank import fetch_wb_country, WB_INDICATORS, WB_WGI
"""

import requests
import time
import json
from typing import Optional

WB_BASE = "https://api.worldbank.org/v2"

# ─────────────────────────────────────────
# 일반 지표 (source 파라미터 불필요) — 16개
# ─────────────────────────────────────────
WB_INDICATORS = {
    # A₁ 민중분노지수
    "poverty_rate":      "SI.POV.DDAY",        # 빈곤율 $2.15/day (%)
    "unemployment":      "SL.UEM.TOTL.ZS",     # 실업률 (%)
    "malnutrition":      "SN.ITK.DEFC.ZS",     # 영양결핍률 (%)

    # S₁ 사회응집 / E₂ 불평등
    "gini":              "SI.POV.GINI",         # 지니계수 (0~100)
    "internet_users":    "IT.NET.USER.ZS",      # 인터넷보급률 (%)

    # E₁ 경제충격지수
    "gdp_growth":        "NY.GDP.MKTP.KD.ZG",  # GDP 성장률 (%)
    "inflation":         "FP.CPI.TOTL.ZG",     # 인플레이션 (%)
    "external_debt":     "DT.DOD.DECT.GN.ZS",  # 외채/GNI (%)

    # G₁ 지정학 / G₂ 군사
    "military_gdp":      "MS.MIL.XPND.GD.ZS",  # 군비/GDP (%)
    "trade_openness":    "NE.TRD.GNFS.ZS",     # 무역개방도 (%)

    # C₁ 기후취약 / C₂ 환경
    "co2_per_capita":    "EN.GHG.CO2.PC.CE.AR5",     # CO₂/인 (톤)
    "forest_area":       "AG.LND.FRST.ZS",     # 산림면적비율 (%)
    "renewable_energy":  "EG.FEC.RNEW.ZS",     # 재생에너지비율 (%)
    "pm25":              "EN.ATM.PM25.MC.M3",   # PM2.5 (μg/m³)

    # 기본 인구·경제
    "population":        "SP.POP.TOTL",         # 총인구
    "gdp_per_capita":    "NY.GDP.PCAP.CD",      # 1인당 GDP (USD)
}

# ─────────────────────────────────────────
# WGI 거버넌스 지표 (source=75 필수) — 4개
# ─────────────────────────────────────────
WB_WGI = {
    # A₂ 제도신뢰 / P₁ 정치안정
    "corruption_ctrl":   "CC.EST",   # 부패통제   (-2.5 ~ +2.5)
    "rule_of_law":       "RL.EST",   # 법치주의   (-2.5 ~ +2.5)
    "pol_stability":     "PV.EST",   # 정치안정   (-2.5 ~ +2.5)
    "gov_effectiveness": "GE.EST",   # 정부효과성 (-2.5 ~ +2.5)
}

# Λ¹² 변수 매핑 (fetch_lambda12.py 슬롯 → WB 키)
LAMBDA12_SLOT_MAP = {
    "A1_poverty":       "poverty_rate",
    "A1_unemployment":  "unemployment",
    "A1_malnutrition":  "malnutrition",
    "A2_corruption":    "corruption_ctrl",
    "A2_rule_of_law":   "rule_of_law",
    "S1_gini":          "gini",
    "S1_internet":      "internet_users",
    "E1_gdp_growth":    "gdp_growth",
    "E1_inflation":     "inflation",
    "E1_ext_debt":      "external_debt",
    "P1_pol_stability": "pol_stability",
    "P1_gov_effect":    "gov_effectiveness",
    "G1_military":      "military_gdp",
    "G1_trade":         "trade_openness",
    "C1_co2":           "co2_per_capita",
    "C1_pm25":          "pm25",
    "C2_forest":        "forest_area",
    "C2_renewable":     "renewable_energy",
    "BASE_pop":         "population",
    "BASE_gdppc":       "gdp_per_capita",
}


def _wb_get(iso2: str, code: str, source: Optional[int] = None,
            mrv: int = 5) -> dict:
    """
    내부 호출 함수 — mrv=5로 최근 5년 중 유효값 탐색
    WGI: source=75 / 일반: source=None
    """
    url    = f"{WB_BASE}/country/{iso2}/indicator/{code}"
    params = {"format": "json", "mrv": mrv, "per_page": mrv}
    if source:
        params["source"] = source

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data and len(data) > 1 and data[1]:
            for item in data[1]:
                if item.get("value") is not None:
                    return {
                        "value": item["value"],
                        "year":  item["date"],
                        "code":  code,
                        "ok":    True,
                    }
    except Exception as e:
        return {"value": None, "year": None, "code": code,
                "ok": False, "error": str(e)}
    return {"value": None, "year": None, "code": code, "ok": False}


def fetch_wb_country(iso2: str, verbose: bool = True) -> dict:
    """
    국가 하나의 WB 지표 전체 수집 (일반 16 + WGI 4 = 20개)

    Args:
        iso2: ISO 3166-1 alpha-2 코드 (예: "NP", "HT", "KR")
        verbose: 진행상황 출력 여부

    Returns:
        {
          "iso2": "NP",
          "indicators": {
            "poverty_rate": {"value": 2.4, "year": "2022", ...},
            "corruption_ctrl": {"value": -0.508, "year": "2023", ...},
            ...
          },
          "collection_rate": 0.75,
          "available_count": 15,
          "total_count": 20,
        }
    """
    if verbose:
        print(f"\n[WorldBank] {iso2} 수집 시작 (20개 지표)")

    results = {}

    # 1) 일반 지표
    for name, code in WB_INDICATORS.items():
        res = _wb_get(iso2, code, source=None)
        results[name] = res
        if verbose:
            status = f"✅ {res['value']:>12.3f} ({res['year']})" if res["ok"] \
                     else f"⚠️  N/A"
            print(f"  {name:<22} {status}")
        time.sleep(0.1)   # 레이트리밋 방지

    # 2) WGI 지표 (source=75)
    for name, code in WB_WGI.items():
        res = _wb_get(iso2, code, source=75)
        results[name] = res
        if verbose:
            status = f"✅ {res['value']:>12.3f} ({res['year']})" if res["ok"] \
                     else f"⚠️  N/A"
            print(f"  {name:<22} {status}  [WGI]")
        time.sleep(0.15)  # WGI는 조금 더 여유

    available = sum(1 for r in results.values() if r.get("ok"))
    total     = len(results)
    rate      = available / total

    if verbose:
        print(f"\n  수집률: {available}/{total} ({rate*100:.0f}%)")

    return {
        "iso2":             iso2,
        "indicators":       results,
        "collection_rate":  rate,
        "available_count":  available,
        "total_count":      total,
    }


def fetch_wb_multi(iso_list: list, verbose: bool = True) -> dict:
    """
    복수 국가 일괄 수집
    국가편 배치 생성 시 사용

    Returns:
        {"NP": {...}, "HT": {...}, ...}
    """
    all_results = {}
    for iso2 in iso_list:
        all_results[iso2] = fetch_wb_country(iso2, verbose=verbose)
        time.sleep(0.5)   # 국가 간 딜레이
    return all_results


def wb_to_lambda12(wb_result: dict) -> dict:
    """
    fetch_wb_country() 결과를 Λ¹² 슬롯 형태로 변환
    fetch_lambda12.py 연동용

    Returns:
        {"A1_poverty": 2.4, "A2_corruption": -0.508, ...}
    """
    indicators = wb_result.get("indicators", {})
    lambda12   = {}
    for slot, wb_key in LAMBDA12_SLOT_MAP.items():
        item = indicators.get(wb_key, {})
        lambda12[slot] = item.get("value")   # None이면 None
    return lambda12


# ─────────────────────────────────────────
# 단독 실행 테스트
# ─────────────────────────────────────────
if __name__ == "__main__":
    # 테스트: 네팔 + 아이티
    test_countries = ["NP", "HT"]

    for iso2 in test_countries:
        result = fetch_wb_country(iso2, verbose=True)
        slots  = wb_to_lambda12(result)

        print(f"\n  Λ¹² 슬롯 변환 ({iso2}):")
        for k, v in slots.items():
            if v is not None:
                print(f"    {k:<22} {v:.3f}")
            else:
                print(f"    {k:<22} None")

    print("\n✅ fetch_worldbank.py 테스트 완료")
    print("   → fetch_lambda12.py에서 import 준비 완료")
