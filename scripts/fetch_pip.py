#!/usr/bin/env python3
"""World Bank PIP API 68개국 빈곤-불평등 데이터 수집
저장: data/bsli/{ISO3}_pip_2023.json

실행: python3 fetch_pip.py [--force]
"""

import json
import subprocess
import sys
import time
from pathlib import Path

COUNTRIES = [
    "AGO","ARE","ARG","AUS","AUT","BEL","BGD","BRA","CAN","CHE",
    "CHL","CHN","CIV","CMR","COD","COL","CZE","DEU","DNK","EGY",
    "ESP","ETH","FIN","FRA","GBR","GHA","GRC","HKG","HUN","IDN",
    "IND","IRN","ISR","ITA","JPN","KEN","KOR","LKA","MAR","MEX",
    "MOZ","MYS","NGA","NLD","NOR","NZL","PAK","PER","PHL","POL",
    "PRT","ROU","RUS","SAU","SEN","SGP","SWE","THA","TUN","TUR",
    "TWN","TZA","UGA","UKR","USA","VNM","ZAF","ZMB",
]

PIP_NOT_SUPPORTED = {"HKG", "SGP", "SAU"}
POVERTY_LINES = [2.15, 3.65, 6.85]
YEAR = 2023
BASE_URL = "https://api.worldbank.org/pip/v1/pip"
OUT_DIR = Path(__file__).parent.parent / "data" / "bsli"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FORCE = "--force" in sys.argv


def fetch_pip(country: str, povline: float, retries: int = 3) -> dict | None:
    url = (
        f"{BASE_URL}?country={country}&year={YEAR}"
        f"&povline={povline}&fill_gaps=true&format=json"
    )
    for attempt in range(retries):
        if attempt > 0:
            time.sleep(1.0 * attempt)
        try:
            r = subprocess.run(
                ["curl", "-s", "--max-time", "20", url],
                capture_output=True, text=True, check=True
            )
            if not r.stdout.strip():
                continue
            data = json.loads(r.stdout)
            if isinstance(data, dict) and "error" in data:
                return None  # 미지원 국가
            if isinstance(data, list) and data:
                return data[0]
        except (json.JSONDecodeError, subprocess.CalledProcessError):
            continue
    return None


def extract_fields(raw: dict | None) -> dict:
    if raw is None:
        return {}
    return {
        "headcount":        raw.get("headcount"),
        "poverty_gap":      raw.get("poverty_gap"),
        "poverty_severity": raw.get("poverty_severity"),
        "mean":             raw.get("mean"),
        "median":           raw.get("median"),
        "gini":             raw.get("gini"),
        "reporting_pop":    raw.get("reporting_pop"),
        "reporting_gdp":    raw.get("reporting_gdp"),
        "reporting_pce":    raw.get("reporting_pce"),
        "is_interpolated":  raw.get("is_interpolated"),
        "estimation_type":  raw.get("estimation_type"),
        "welfare_type":     raw.get("welfare_type"),
        "survey_year":      raw.get("survey_year"),
    }


def collect_country(code: str) -> dict:
    if code in PIP_NOT_SUPPORTED:
        return {
            "country": code,
            "year": YEAR,
            "pip_supported": False,
            "note": "PIP 미지원 (고소득 비조사국)",
            "poverty_lines": {},
            "gini": None, "mean_consumption": None,
            "median_consumption": None, "reporting_gdp": None,
            "reporting_pop": None, "welfare_type": None,
        }

    pl_results = {}
    for pl in POVERTY_LINES:
        key = f"usd{str(pl).replace('.', '_')}"
        raw = fetch_pip(code, pl)
        pl_results[key] = extract_fields(raw)
        time.sleep(0.5)

    # gini/mean/gdp 등 poverty-line 무관 값: 데이터 있는 첫 번째 결과에서 추출
    ref = {}
    for key in ["usd2_15", "usd3_65", "usd6_85"]:
        candidate = pl_results.get(key, {})
        if candidate.get("mean") is not None:
            ref = candidate
            break

    return {
        "country": code,
        "year": YEAR,
        "pip_supported": True,
        "poverty_lines": {k: pl_results.get(k, {}) for k in ["usd2_15", "usd3_65", "usd6_85"]},
        "gini":               ref.get("gini"),
        "mean_consumption":   ref.get("mean"),
        "median_consumption": ref.get("median"),
        "reporting_gdp":      ref.get("reporting_gdp"),
        "reporting_pop":      ref.get("reporting_pop"),
        "welfare_type":       ref.get("welfare_type"),
    }


def main():
    todo = [c for c in COUNTRIES
            if FORCE or not (OUT_DIR / f"{c}_pip_{YEAR}.json").exists()]
    skip_count = len(COUNTRIES) - len(todo)
    print(f"PIP 수집 — {len(todo)}개국 수집 / {skip_count}개국 기존 파일 재사용\n")

    failed = []
    for i, code in enumerate(todo, 1):
        print(f"[{i:02d}/{len(todo)}] {code} ...", end=" ", flush=True)
        try:
            data = collect_country(code)
            path = OUT_DIR / f"{code}_pip_{YEAR}.json"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

            hc685 = data["poverty_lines"].get("usd6_85", {}).get("headcount")
            hc215 = data["poverty_lines"].get("usd2_15", {}).get("headcount")
            gini  = data.get("gini")
            mean  = data.get("mean_consumption")

            if not data["pip_supported"]:
                print("미지원")
            else:
                print(f"hc(2.15)={hc215}  hc(6.85)={hc685}  gini={gini}  mean={mean}")
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append(code)

    # 전체 summary (기존 파일 포함)
    all_data = {}
    for code in COUNTRIES:
        path = OUT_DIR / f"{code}_pip_{YEAR}.json"
        if path.exists():
            all_data[code] = json.loads(path.read_text())

    summary_countries = {}
    for code, d in all_data.items():
        summary_countries[code] = {
            "supported":      d.get("pip_supported"),
            "headcount_215":  d.get("poverty_lines", {}).get("usd2_15", {}).get("headcount"),
            "headcount_365":  d.get("poverty_lines", {}).get("usd3_65", {}).get("headcount"),
            "headcount_685":  d.get("poverty_lines", {}).get("usd6_85", {}).get("headcount"),
            "gini":           d.get("gini"),
            "mean":           d.get("mean_consumption"),
            "gdp_pc":         d.get("reporting_gdp"),
            "pop":            d.get("reporting_pop"),
            "welfare_type":   d.get("welfare_type"),
        }

    summary_path = OUT_DIR / f"_summary_{YEAR}.json"
    summary_path.write_text(json.dumps({
        "year":          YEAR,
        "total":         len(COUNTRIES),
        "collected":     len([v for v in summary_countries.values() if v["supported"]]),
        "not_supported": len([v for v in summary_countries.values() if v["supported"] is False]),
        "failed":        failed,
        "countries":     summary_countries,
    }, ensure_ascii=False, indent=2))

    print(f"\n완료 → {summary_path}")
    if failed:
        print(f"실패 국가: {failed}")


if __name__ == "__main__":
    main()
