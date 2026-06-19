#!/usr/bin/env python3
"""
BSLI 전체국 파이프라인
pip_owid.csv → ISO_TO_PIP 전체 매핑 → BSLI 공식 적용 → JSON/CSV 저장
공식: BSLI = 0.40·F_ML + 0.60·H − D − Hs

Usage: python3 tools/fetch_bsli.py
"""

import csv
import json
import os
from datetime import date

# ── 경로 ────────────────────────────────────────────────────
PIP_CSV  = os.path.expanduser("~/everbluesea/data/bsli/pip_owid.csv")
OUT_DIR  = os.path.expanduser("~/everbluesea/data/bsli")
OUT_JSON = os.path.join(OUT_DIR, "bsli_all_2023.json")
OUT_CSV  = os.path.join(OUT_DIR, "bsli_all_2023.csv")

TARGET_YEAR    = 2023   # 없으면 최근 연도 fallback
FALLBACK_YEARS = 10    # 2013~2023 커버 (Japan 2013, UAE 2013, Morocco 2013 등 포함)

# ── WTO ISO3 → PIP 국가명 매핑 ──────────────────────────────
ISO_TO_PIP = {
    # 유럽
    "FRA": "France",
    "GBR": "United Kingdom",
    "CHE": "Switzerland",
    "NLD": "Netherlands",
    "BEL": "Belgium",
    "AUT": "Austria",
    "DEU": "Germany",
    "SWE": "Sweden",
    "NOR": "Norway",
    "DNK": "Denmark",
    "FIN": "Finland",
    "ITA": "Italy",
    "ESP": "Spain",
    "PRT": "Portugal",
    "GRC": "Greece",
    "POL": "Poland",
    "CZE": "Czechia",
    "HUN": "Hungary",
    "ROU": "Romania",
    "RUS": "Russia",
    "TUR": "Turkey",
    "UKR": "Ukraine",
    # 아시아
    "CHN": "China",
    "JPN": "Japan",
    "KOR": "South Korea",
    "TWN": "Taiwan",
    "HKG": None,            # PIP 없음
    "SGP": None,            # PIP 없음 (고소득, 설문 없음)
    "THA": "Thailand",
    "VNM": "Vietnam",
    "IDN": "Indonesia",
    "MYS": "Malaysia",
    "PHL": "Philippines",
    "IND": "India",
    "BGD": "Bangladesh",
    "PAK": "Pakistan",
    "LKA": "Sri Lanka",
    "SAU": None,            # PIP 없음
    "ARE": "United Arab Emirates",
    "ISR": "Israel",
    "IRN": "Iran",
    # 아메리카 + 오세아니아
    "USA": "United States",
    "CAN": "Canada",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "CHL": "Chile",
    "COL": "Colombia",
    "PER": "Peru",
    "AUS": "Australia",
    "NZL": None,            # PIP 없음 (고소득)
    # 아프리카
    "EGY": "Egypt",
    "MAR": "Morocco",
    "TUN": "Tunisia",
    "NGA": "Nigeria",
    "GHA": "Ghana",
    "SEN": "Senegal",
    "CIV": "Cote d'Ivoire",
    "ETH": "Ethiopia",
    "KEN": "Kenya",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "ZAF": "South Africa",
    "MOZ": "Mozambique",
    "ZMB": "Zambia",
    "AGO": "Angola",
    "CMR": "Cameroon",
    "COD": "Democratic Republic of Congo",
    # ── 추가: 동유럽 / 발칸 / 코카서스 / 중앙아시아 ────────────
    "ALB": "Albania",
    "ARM": "Armenia",
    "BLR": "Belarus",
    "BGR": "Bulgaria",
    "HRV": "Croatia",
    "CYP": "Cyprus",
    "EST": "Estonia",
    "GEO": "Georgia",
    "KAZ": "Kazakhstan",
    "XKX": "Kosovo",
    "KGZ": "Kyrgyzstan",
    "LVA": "Latvia",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "MDA": "Moldova",
    "MNE": "Montenegro",
    "MKD": "North Macedonia",
    "SRB": "Serbia",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "TJK": "Tajikistan",
    # ── 추가: 중동 / 남아시아 추가 ──────────────────────────────
    "MMR": "Myanmar",
    "MNG": "Mongolia",
    "BTN": "Bhutan",
    "PSE": "Palestine",
    "YEM": "Yemen",
    # ── 추가: 동남아시아 / 오세아니아 추가 ─────────────────────
    "LAO": "Laos",
    "TLS": "Timor",
    "FJI": "Fiji",
    "KIR": "Kiribati",
    "MDV": "Maldives",
    "MHL": "Marshall Islands",
    "FSM": "Micronesia (country)",
    "WSM": "Samoa",
    "TON": "Tonga",
    "VUT": "Vanuatu",
    # ── 추가: 중남미 추가 ────────────────────────────────────────
    "BOL": "Bolivia",
    "CRI": "Costa Rica",
    "DOM": "Dominican Republic",
    "ECU": "Ecuador",
    "SLV": "El Salvador",
    "GTM": "Guatemala",
    "HND": "Honduras",
    "NIC": "Nicaragua",
    "PAN": "Panama",
    "PRY": "Paraguay",
    "URY": "Uruguay",
    "LCA": "Saint Lucia",
    # ── 추가: 아프리카 추가 ──────────────────────────────────────
    "BEN": "Benin",
    "BFA": "Burkina Faso",
    "BDI": "Burundi",
    "CPV": "Cape Verde",
    "TCD": "Chad",
    "COM": "Comoros",
    "DJI": "Djibouti",
    "SWZ": "Eswatini",
    "GAB": "Gabon",
    "GMB": "Gambia",
    "GIN": "Guinea",
    "GNB": "Guinea-Bissau",
    "LSO": "Lesotho",
    "LBR": "Liberia",
    "MWI": "Malawi",
    "MLI": "Mali",
    "MRT": "Mauritania",
    "MUS": "Mauritius",
    "NAM": "Namibia",
    "NER": "Niger",
    "RWA": "Rwanda",
    "SYC": "Seychelles",
    "SLE": "Sierra Leone",
    "SOM": "Somalia",
    "SSD": "South Sudan",
    "SDN": "Sudan",
    "TGO": "Togo",
    "BWA": "Botswana",
    "ZWE": "Zimbabwe",
    # ── 추가: 서유럽 추가 ────────────────────────────────────────
    "IRL": "Ireland",
    "ISL": "Iceland",
    "MLT": "Malta",
}

# ── PIP 데이터 로드 ──────────────────────────────────────────

def load_pip(path: str) -> dict:
    """
    {pip_country_name: {year: {col: value}}} 구조로 로드
    reporting_level='national' 우선, welfare_type 무관
    ppp_version=2017 우선, 없으면 2011도 허용 (ppp 필터 완전 제거)
    """
    data = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 지역 집계 행 제외
            country = row["country"]
            if any(kw in country for kw in ["and ", "income", "Asia", "Africa",
                                             "Europe", "America", "World", "South Asia"]):
                # 단, 국가명 예외
                if country not in ("South Korea", "South Africa", "South Sudan"):
                    continue

            rl       = row.get("reporting_level", "")
            ppp      = row.get("ppp_version", "")
            year_str = row.get("year", "")

            # reporting_level: national 우선, all 허용
            if rl not in ("national", "all", ""):
                continue

            try:
                year = int(float(year_str))
            except (ValueError, TypeError):
                continue

            if country not in data:
                data[country] = {}

            # 중복 행: national > all, ppp=2017 > 2011 우선
            if year in data[country]:
                existing_rl  = data[country][year].get("_rl", "")
                existing_ppp = data[country][year].get("_ppp", "")
                # 기존이 national, 새게 national 아님 → 건너뜀
                if existing_rl == "national" and rl != "national":
                    continue
                # rl 동등하고 기존이 2017, 새게 2017 아님 → 건너뜀
                if existing_rl == rl and existing_ppp == "2017" and ppp != "2017":
                    continue

            data[country][year] = {k: v for k, v in row.items()}
            data[country][year]["_rl"]  = rl
            data[country][year]["_ppp"] = ppp

    return data


def get_row(pip_data: dict, pip_name: str, target_year: int,
            fallback_years: int = FALLBACK_YEARS) -> dict | None:
    """타겟 연도 우선, 없으면 [target_year-fallback_years, target_year) 내 최신 연도 fallback"""
    if pip_name not in pip_data:
        return None
    years = pip_data[pip_name]
    if target_year in years:
        return years[target_year]
    # fallback: target_year 이전 fallback_years 내 가장 최근 연도
    candidates = [y for y in years if target_year - fallback_years <= y < target_year]
    if candidates:
        return years[max(candidates)]
    return None


def safe_float(val) -> float | None:
    try:
        v = float(val)
        return v if v == v else None   # NaN 제거
    except (TypeError, ValueError):
        return None


# ── BSLI 공식 ────────────────────────────────────────────────
# BSLI = 0.40·F_ML + 0.60·H − D − Hs
#
# F_ML = 소득 3~5분위 평균 활력 (decile3_avg~decile5_avg 평균, 정규화)
# H    = 중위소득 (median, 정규화)
# D    = 빈곤율 $3.65 기준 (headcount_ratio_lower_mid_income_povline)
# Hs   = 소득 불평등 압력 (palma_ratio, 정규화)

def extract_raw(row: dict) -> dict:
    """원시값 추출"""
    d3 = safe_float(row.get("decile3_avg"))
    d4 = safe_float(row.get("decile4_avg"))
    d5 = safe_float(row.get("decile5_avg"))

    present = [v for v in [d3, d4, d5] if v is not None]
    f_ml_raw = sum(present) / len(present) if present else None

    return {
        "F_ML_raw":  f_ml_raw,
        "H_raw":     safe_float(row.get("median")),
        "D_raw":     safe_float(row.get("headcount_ratio_lower_mid_income_povline")),
        "Hs_raw":    safe_float(row.get("palma_ratio")),
        "gini":      safe_float(row.get("gini")),
        "mean":      safe_float(row.get("mean")),
        "year_used": int(float(row.get("year", 0))),
        "_rl":       row.get("_rl", ""),
        "_ppp":      row.get("_ppp", ""),
    }


def normalize_series(records: list[dict], key: str, inverse: bool = False) -> None:
    """전체 68개국 기준 min-max 정규화 (in-place)"""
    vals = [r[key] for r in records if r[key] is not None]
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    for r in records:
        v = r[key]
        if v is None:
            r[key + "_norm"] = None
        elif hi == lo:
            r[key + "_norm"] = 0.5
        else:
            s = (v - lo) / (hi - lo)
            r[key + "_norm"] = round(1.0 - s if inverse else s, 4)


def calc_bsli(r: dict) -> float | None:
    f = r.get("F_ML_raw_norm")
    h = r.get("H_raw_norm")
    d = r.get("D_raw_norm")
    hs = r.get("Hs_raw_norm")
    if any(v is None for v in [f, h, d, hs]):
        return None
    val = 0.40 * f + 0.60 * h - d - hs
    return round(val, 4)


# ── 메인 ─────────────────────────────────────────────────────

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    print(f"PIP 데이터 로드 중: {PIP_CSV}")
    pip_data = load_pip(PIP_CSV)
    print(f"  PIP 로드 완료: {len(pip_data)}개 국가명")

    print(f"  fallback_years = {FALLBACK_YEARS} (범위: {TARGET_YEAR - FALLBACK_YEARS}~{TARGET_YEAR})\n")

    # 1단계: 원시값 수집
    records = []
    missing_pip = []

    for iso, pip_name in ISO_TO_PIP.items():
        if pip_name is None:
            print(f"  [{iso}] PIP 없음 — 건너뜀")
            missing_pip.append(iso)
            continue

        row = get_row(pip_data, pip_name, TARGET_YEAR)
        if row is None:
            print(f"  [{iso}] {pip_name} — 데이터 없음 ({TARGET_YEAR - FALLBACK_YEARS}년 이전)")
            missing_pip.append(iso)
            continue

        raw = extract_raw(row)
        raw["iso"] = iso
        raw["pip_name"] = pip_name
        # reliability: 실제 사용 연도 기반
        raw["reliability"] = "ok" if raw["year_used"] == TARGET_YEAR else "fallback_10yr"
        records.append(raw)
        ppp_tag = f"ppp={raw['_ppp']}" if raw["_ppp"] else ""
        rel_tag = f"[{raw['reliability']}]" if raw["reliability"] != "ok" else ""
        if all(v is not None for v in [raw["F_ML_raw"], raw["H_raw"],
                                        raw["D_raw"],   raw["Hs_raw"]]):
            print(f"  [{iso}] {pip_name} ({raw['year_used']} {ppp_tag}) {rel_tag}  "
                  f"F_ML={raw['F_ML_raw']:.2f}  H={raw['H_raw']:.2f}  "
                  f"D={raw['D_raw']:.1f}%  Hs={raw['Hs_raw']:.2f}")
        else:
            print(f"  [{iso}] {pip_name} ({raw['year_used']} {ppp_tag}) {rel_tag} — 일부 결측")

    print(f"\n  수집 완료: {len(records)}개국 / 제외: {len(missing_pip)}개국")
    print(f"  제외 목록: {', '.join(missing_pip)}\n")

    # 2단계: 전체 기준 정규화
    normalize_series(records, "F_ML_raw", inverse=False)
    normalize_series(records, "H_raw",    inverse=False)
    normalize_series(records, "D_raw",    inverse=False)   # 빈곤율: 높을수록 나쁨 → 감산
    normalize_series(records, "Hs_raw",   inverse=False)   # palma: 높을수록 불평등 → 감산

    # 3단계: BSLI 계산
    for r in records:
        r["BSLI"] = calc_bsli(r)

    # 정렬
    records.sort(key=lambda x: (-(x["BSLI"] or -9999)))

    # 4단계: JSON 저장
    n_fallback = sum(1 for r in records if r["reliability"] == "fallback_10yr")
    output = {
        "version":        "BSLI_v3.2",
        "target_year":    TARGET_YEAR,
        "fallback_years": FALLBACK_YEARS,
        "updated":        date.today().isoformat(),
        "formula":        "BSLI = 0.40·F_ML + 0.60·H − D − Hs",
        "note":           f"정규화 기준: 수집된 전체 국가 (pip_owid 전체 매핑) | "
                          f"fallback: {TARGET_YEAR - FALLBACK_YEARS}~{TARGET_YEAR} (10년) | "
                          f"fallback_10yr 적용: {n_fallback}개국",
        "countries": []
    }
    for r in records:
        output["countries"].append({
            "iso":         r["iso"],
            "name":        r["pip_name"],
            "year_used":   r["year_used"],
            "ppp_used":    r["_ppp"],
            "reliability": r["reliability"],
            "BSLI":        r["BSLI"],
            "components": {
                "F_ML":  r.get("F_ML_raw_norm"),
                "H":     r.get("H_raw_norm"),
                "D":     r.get("D_raw_norm"),
                "Hs":    r.get("Hs_raw_norm"),
            },
            "raw": {
                "F_ML_raw": round(r["F_ML_raw"], 4) if r["F_ML_raw"] else None,
                "H_raw":    round(r["H_raw"], 4)    if r["H_raw"]    else None,
                "D_pct":    round(r["D_raw"], 4)    if r["D_raw"]    else None,
                "Hs_palma": round(r["Hs_raw"], 4)   if r["Hs_raw"]   else None,
                "gini":     round(r["gini"], 4)      if r["gini"]     else None,
            }
        })

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 5단계: CSV 저장
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "iso", "name", "year_used", "ppp_used", "reliability", "BSLI",
                    "F_ML", "H", "D", "Hs", "gini", "F_ML_raw", "H_raw", "D_pct", "Hs_palma"])
        for rank, r in enumerate(records, 1):
            c = output["countries"][rank - 1]
            w.writerow([
                rank,
                c["iso"], c["name"], c["year_used"], c["ppp_used"], c["reliability"],
                c["BSLI"],
                c["components"]["F_ML"], c["components"]["H"],
                c["components"]["D"],   c["components"]["Hs"],
                c["raw"]["gini"],
                c["raw"]["F_ML_raw"],   c["raw"]["H_raw"],
                c["raw"]["D_pct"],      c["raw"]["Hs_palma"],
            ])

    # 6단계: 순위 출력
    print(f"\n{'═'*78}")
    print(f"  BSLI 순위 (TARGET={TARGET_YEAR}, fallback {FALLBACK_YEARS}년, {len(records)}개국 / fallback적용 {n_fallback}개국)")
    print(f"{'═'*78}")
    print(f"  {'순위':>4}  {'ISO':4}  {'연도':>4}  {'ppp':>4}  {'신뢰도':<14}  {'BSLI':>7}  "
          f"{'F_ML':>6}  {'H':>6}  {'D':>6}  {'Hs':>6}  국가명")
    print(f"  {'─'*90}")
    for rank, r in enumerate(records, 1):
        c = output["countries"][rank - 1]
        comp = c["components"]
        bsli_str = f"{c['BSLI']:>7.4f}" if c["BSLI"] is not None else f"{'N/A':>7}"
        print(f"  {rank:>4}  {c['iso']:4}  {c['year_used']:>4}  {c['ppp_used']:>4}  "
              f"{c['reliability']:<14}  {bsli_str}  "
              f"{comp['F_ML'] or 0:>6.3f}  "
              f"{comp['H'] or 0:>6.3f}  "
              f"{comp['D'] or 0:>6.3f}  "
              f"{comp['Hs'] or 0:>6.3f}  "
              f"{c['name']}")

    print(f"\n저장 완료:")
    print(f"  JSON: {OUT_JSON}")
    print(f"  CSV:  {OUT_CSV}")
    print(f"  총 {len(records)}개국 (ok: {len(records)-n_fallback}, fallback_10yr: {n_fallback}) / 제외 {len(missing_pip)}개국\n")


if __name__ == "__main__":
    main()
