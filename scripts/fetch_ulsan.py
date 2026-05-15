"""
DURE-η 통합 데이터 파이프라인
KOSIS(인구/고용/복지) + SGIS(행정경계 GeoJSON) → data/ulsan.json
"""
from __future__ import annotations
import json, sys, time, os
from pathlib import Path
import requests

# ── 인증키 ──────────────────────────────────────────
KOSIS_KEY   = os.environ.get("KOSIS_API_KEY", "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
SGIS_KEY    = os.environ.get("SGIS_CONSUMER_KEY",    "a7f9a200a67241698800")
SGIS_SECRET = os.environ.get("SGIS_CONSUMER_SECRET", "7509589f1d3142d586b2")

# ── 경로 ────────────────────────────────────────────
OUTPUT = Path("data/ulsan.json")

# ── KOSIS 테이블 ────────────────────────────────────
KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
KOSIS_TABLES = [
    {
        "label": "울산_구군별_인구",
        "params": {
            "method": "getList", "apiKey": KOSIS_KEY,
            "format": "json", "jsonVD": "Y",
            "orgId": "101", "tblId": "DT_1B040A3",
            "itmId": "T20 T21 T22",
            "objL1": "31110 31120 31140 31170 31710",
            "prdSe": "M", "newEstPrdCnt": "3",
        },
    },
]

# ── SGIS 함수 ────────────────────────────────────────
def sgis_token() -> str | None:
    url = (
        "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json"
        f"?consumer_key={SGIS_KEY}&consumer_secret={SGIS_SECRET}"
    )
    r = requests.get(url, timeout=10)
    data = r.json()
    if data.get("errCd") == 0:
        token = data["result"]["accessToken"]
        print(f"  SGIS token OK: {token[:8]}...")
        return token
    print(f"  SGIS token FAIL: {data}")
    return None

def sgis_boundary(token: str) -> dict | None:
    url = (
        "https://sgisapi.kostat.go.kr/OpenAPI3/boundary/hadmarea.geojson"
        f"?accessToken={token}&year=2023&adm_cd=26&low_search=1"
    )
    r = requests.get(url, timeout=15)
    data = r.json()
    if data.get("errCd") == 0:
        count = len(data.get("features", []))
        print(f"  SGIS boundary OK: {count} features")
        return data
    print(f"  SGIS boundary FAIL: {data.get('errMsg')}")
    return None

# ── KOSIS 수집 ───────────────────────────────────────
def collect_kosis() -> dict:
    results = {}
    for table in KOSIS_TABLES:
        label = table["label"]
        print(f"\n[KOSIS] {label}")
        try:
            resp = requests.get(KOSIS_BASE, params=table["params"], timeout=15)
            data = resp.json()
            if isinstance(data, dict) and "err" in data:
                print(f"  SKIP: {data.get('errMsg')}")
                results[label] = {"error": data.get("errMsg")}
            else:
                rows = len(data) if isinstance(data, list) else 0
                print(f"  OK: {rows} rows")
                results[label] = {"row_count": rows, "data": data}
        except Exception as e:
            print(f"  ERR: {e}")
            results[label] = {"error": str(e)}
        time.sleep(0.5)
    return results

# ── 메인 ────────────────────────────────────────────
def main() -> int:
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    print("=" * 50)
    print(f"DURE-η 파이프라인 시작: {now}")
    print("=" * 50)

    result = {"_updated": now}

    # 1. KOSIS
    print("\n[1] KOSIS 수집")
    result["kosis"] = collect_kosis()

    # 2. SGIS
    print("\n[2] SGIS 수집")
    token = sgis_token()
    if token:
        boundary = sgis_boundary(token)
        result["sgis"] = {
            "boundary": boundary,
            "adm_cd":   "26",
            "year":     "2023",
        }
    else:
        result["sgis"] = {"error": "token 발급 실패"}

    # 3. 저장
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 저장 완료 → {OUTPUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
