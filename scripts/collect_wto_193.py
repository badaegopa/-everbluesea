#!/usr/bin/env python3
"""
collect_wto_193.py — UN 193개국 WTO 데이터 일괄 수집 러너
늘푸른바다 사회동역학연구소 · Λ¹² 모천(母川) 데이터 수집

[설계 원칙 — 청해 2026-06-28]
  · 한 나라도 버리지 않는다. 데이터가 비어도 명단에 이름을 남긴다.
  · 결측은 보간하지 않는다. 빈 것은 "조회 안 됨"으로 명시한다.
  · 빈 패턴 자체가 그 사회의 상태를 말하는 신호다 — 관찰 대상.

[4가지 안전장치]
  ① 재시도: 실패 시 3회까지, 2→4→6초 대기 (일시적 끊김 흡수)
  ② 이어받기: 이미 받은 나라(파일 존재 + 정상)는 건너뜀 (--force로 재수집)
  ③ 결측 명시: null 지표를 missing 목록에 기록 (보간 없음)
  ④ 요약 리포트: 전체 수집 후 국가별 N/15 + 데이터 사각지대 집계

사용법 (AI PC PowerShell):
  python collect_wto_193.py                 # 전체 193개국 (이어받기)
  python collect_wto_193.py --region 유럽    # 특정 권역만
  python collect_wto_193.py --force          # 이미 받은 것도 다시
  python collect_wto_193.py --year 2023      # 기준연도 지정(기본 2023)
"""
from __future__ import annotations
import argparse, json, os, sys, time
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import requests   # certifi 내장 → SSL 문제 없음 (urllib 대신 사용)

# ── 설정 ──────────────────────────────────────────────────────
API_KEY  = "e5769b9320a24c4db1430476871cb558"
BASE_URL = "https://api.wto.org/timeseries/v1"
PARTNER_ALL = "000"
YEAR_DEFAULT = 2023

HTTP_TIMEOUT = 30
MAX_RETRIES  = 3
RETRY_WAITS  = [2, 4, 6]
POLITE_GAP   = 0.3   # 지표 간 대기(초) — WTO 예의상 간격
COUNTRY_GAP  = 1.0   # 국가 간 대기(초)

# 코드집 경로 (이 스크립트와 같은 폴더의 un193_codes.json)
SCRIPT_DIR = Path(__file__).resolve().parent
CODES_PATH = SCRIPT_DIR / "un193_codes.json"
# 출력 폴더 (Windows/Linux 모두 동작하도록 상대경로 우선)
OUT_DIR = Path("data/wto")

# ── WTO 15개 지표 (fetch_wto_api.py와 동일) ──────────────────
INDICATORS = {
    "trade":    ["ITS_MTV_AX", "ITS_MTV_AM", "ITS_MTP_AXVG", "ITS_MTP_AMVG"],
    "tariff":   ["TP_A_0010", "TP_A_0160", "TP_A_0430", "TP_B_0020", "TP_B_0090"],
    "services": ["ITS_CS_QAX", "ITS_CS_QAM", "BAT_BV_X", "BAT_BV_M"],
    "price":    ["ITS_MTP_AUVX", "ITS_MTP_AUVM"],
}
ALL_INDICATORS = [i for g in INDICATORS.values() for i in g]
NO_PARTNER = set(INDICATORS["tariff"])          # 관세 지표는 partner 파라미터 없음
NO_PERIOD  = {"TP_B_0020", "TP_B_0090"}         # 양허관세는 기간 차원 없음

# 지표 한글 이름 (요약 출력용)
IND_NAME = {
    "ITS_MTV_AX": "상품수출액", "ITS_MTV_AM": "상품수입액",
    "ITS_MTP_AXVG": "수출물량증가율", "ITS_MTP_AMVG": "수입물량증가율",
    "TP_A_0010": "단순평균실행관세", "TP_A_0160": "가중평균실행관세",
    "TP_A_0430": "무관세품목비중", "TP_B_0020": "단순평균양허관세",
    "TP_B_0090": "양허범위", "ITS_CS_QAX": "서비스수출액",
    "ITS_CS_QAM": "서비스수입액", "BAT_BV_X": "서비스수지(대변)",
    "BAT_BV_M": "서비스수지(차변)", "ITS_MTP_AUVX": "수출단가지수",
    "ITS_MTP_AUVM": "수입단가지수",
}


def fetch_one(indicator: str, numeric: str, year: int) -> dict | None:
    """단일 지표 1개국 수집 + 재시도. 성공 시 {value, year, unit}, 실패/무자료 시 None."""
    r_code = numeric.zfill(3)
    params = {"i": indicator, "r": r_code, "fmt": "json", "max": "1"}
    if indicator not in NO_PARTNER:
        params["p"] = PARTNER_ALL
    if indicator not in NO_PERIOD:
        params["ps"] = str(year)
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(f"{BASE_URL}/data", params=params,
                             headers=headers, timeout=HTTP_TIMEOUT)
            if r.status_code != 200:
                # HTTP 에러도 재시도 (429 rate-limit, 5xx 일시장애 등)
                raise RuntimeError(f"HTTP {r.status_code}")
            data = r.json() if r.text.strip() else None
            if not data or "Dataset" not in data or not data["Dataset"]:
                return None   # 데이터 없음 (에러 아님 — 그 나라가 그 지표를 안 냄)
            row = data["Dataset"][0]
            return {"value": row.get("Value"),
                    "year": row.get("Year"),
                    "unit": row.get("UnitSymbol", "")}
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAITS[min(attempt - 1, len(RETRY_WAITS) - 1)])
    # 모든 재시도 실패 → None (수집 실패로 기록되되 전체는 계속)
    print(f"      ! {indicator} 재시도 {MAX_RETRIES}회 모두 실패: "
          f"{type(last_exc).__name__}", flush=True)
    return None


def collect_country(numeric: str, iso3: str, name: str, region: str,
                    year: int) -> dict:
    """1개국 15지표 수집. 결측은 missing 목록에 명시 기록(보간 없음)."""
    indicators_data = {}
    missing = []   # 조회 안 된 지표 코드 목록 (청해 원칙: 명시)
    ok = 0
    for idx, ind in enumerate(ALL_INDICATORS, 1):
        res = fetch_one(ind, numeric, year)
        if res and res.get("value") is not None:
            indicators_data[ind] = res
            ok += 1
        else:
            indicators_data[ind] = None
            missing.append(ind)
        if idx < len(ALL_INDICATORS):
            time.sleep(POLITE_GAP)

    grouped = {g: {m: indicators_data.get(m) for m in members}
               for g, members in INDICATORS.items()}

    return {
        "numeric": numeric,
        "iso_code": iso3,
        "name": name,
        "region": region,
        "year": year,
        "updated": date.today().isoformat(),
        "collected": ok,
        "total": len(ALL_INDICATORS),
        "missing": missing,   # ★ 조회 안 된 지표 명시 (보간 없음)
        "missing_named": [IND_NAME.get(m, m) for m in missing],
        "indicators": grouped,
    }


def already_done(path: Path) -> int | None:
    """이미 받은 파일이 정상이면 collected 수 반환, 아니면 None."""
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d.get("collected", None)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="UN 193개국 WTO 일괄 수집")
    ap.add_argument("--year", type=int, default=YEAR_DEFAULT)
    ap.add_argument("--region", default=None, help="특정 권역만 (예: 유럽)")
    ap.add_argument("--force", action="store_true", help="이미 받은 것도 재수집")
    args = ap.parse_args()

    KST = timezone(timedelta(hours=9))
    started = datetime.now(KST)
    print("=" * 60)
    print(f"  Λ¹² 모천 수집 — UN 193개국 WTO 데이터")
    print(f"  기준연도: {args.year} · 시작: {started.strftime('%Y-%m-%d %H:%M KST')}")
    print("=" * 60)

    # 코드집 로드
    if not CODES_PATH.exists():
        print(f"✗ 코드집 없음: {CODES_PATH}")
        print("  → un193_codes.json 을 이 스크립트와 같은 폴더에 두세요.")
        return 1
    codes = json.loads(CODES_PATH.read_text(encoding="utf-8"))

    # 권역 필터
    targets = [(num, info) for num, info in codes.items()
               if args.region is None or info["region"] == args.region]
    if not targets:
        print(f"✗ 해당 권역 없음: {args.region}")
        print(f"  사용 가능 권역: {sorted(set(i['region'] for i in codes.values()))}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(targets)
    print(f"\n대상: {total}개국"
          + (f" (권역: {args.region})" if args.region else " (전체)") + "\n")

    results = {}   # iso3 → collected 수 (요약용)
    skipped = 0
    for i, (numeric, info) in enumerate(targets, 1):
        iso3, name, region = info["iso3"], info["name"], info["region"]
        out_path = OUT_DIR / f"{iso3}_{args.year}.json"

        # ② 이어받기
        if not args.force:
            done = already_done(out_path)
            if done is not None:
                print(f"[{i:3d}/{total}] {iso3} {name[:20]:20s} "
                      f"이미받음 {done}/15 ⏭", flush=True)
                results[iso3] = done
                skipped += 1
                continue

        print(f"[{i:3d}/{total}] {iso3} {name[:20]:20s} [{region}] 수집중...",
              flush=True)
        data = collect_country(numeric, iso3, name, region, args.year)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        results[iso3] = data["collected"]

        # 진행 표시
        miss = (" · 결측: " + ", ".join(data["missing_named"])
                if data["missing"] else "")
        print(f"          → {data['collected']}/15{miss}", flush=True)

        time.sleep(COUNTRY_GAP)

    # ④ 요약 리포트
    ended = datetime.now(KST)
    elapsed = (ended - started).total_seconds()
    print("\n" + "=" * 60)
    print(f"  수집 완료 — {len(results)}개국 / 소요 {elapsed/60:.1f}분"
          + (f" (이어받기 {skipped}개국 생략)" if skipped else ""))
    print("=" * 60)

    # 데이터 충실도 구간별 집계
    full   = [k for k, v in results.items() if v == 15]
    most   = [k for k, v in results.items() if 11 <= v <= 14]
    half   = [k for k, v in results.items() if 6 <= v <= 10]
    sparse = [k for k, v in results.items() if 1 <= v <= 5]
    empty  = [k for k, v in results.items() if v == 0]

    print(f"\n  ■ 데이터 충실도 지도")
    print(f"    완전 (15/15)      : {len(full):3d}개국")
    print(f"    풍부 (11~14)      : {len(most):3d}개국")
    print(f"    절반 (6~10)       : {len(half):3d}개국")
    print(f"    희소 (1~5)        : {len(sparse):3d}개국")
    print(f"    사각지대 (0/15)   : {len(empty):3d}개국  ← 별도 데이터 경로 필요")

    if empty:
        print(f"\n  ★ 데이터 사각지대 (0개 — 명단엔 남기되 다른 API로 보완):")
        print(f"    {', '.join(sorted(empty))}")
    if sparse:
        print(f"\n  ▲ 희소 국가 (1~5개 — 결측 패턴 관찰 대상):")
        print(f"    {', '.join(sorted(sparse))}")

    print(f"\n  저장 위치: {OUT_DIR.resolve()}")
    print(f"  다음 단계: save_country_scores.py 로 η 산출\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
