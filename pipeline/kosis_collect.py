"""
KOSIS OpenAPI - 울산광역시 통계 수집 (requests 버전)
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import os
import requests

API_KEY = os.environ.get("KOSIS_API_KEY", "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
BASE_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
OUTPUT_PATH = Path("/mnt/d/연구소/data/KOSIS/ulsan_raw.json")

TABLES: list[dict] = [
    {
        "label": "울산_인구_월별",
        "params": {
            "method": "getList",
            "apiKey": API_KEY,
            "format": "json",
            "jsonVD": "Y",
            "orgId": "101",
            "tblId": "DT_1B040A3",
            "itmId": "T20 T21 T22",
            "objL1": "31",
            "prdSe": "M",
            "newEstPrdCnt": "12",
        },
    },
    {
        "label": "울산_구군별_인구",
        "params": {
            "method": "getList",
            "apiKey": API_KEY,
            "format": "json",
            "jsonVD": "Y",
            "orgId": "101",
            "tblId": "DT_1B040A3",
            "itmId": "T20 T21 T22",
            "objL1": "31110 31120 31140 31170 31710",
            "prdSe": "M",
            "newEstPrdCnt": "12",
        },
    },
]

def collect() -> dict:
    results: dict = {}
    total_ok = total_skip = total_err = 0

    for table in TABLES:
        label = table["label"]
        print(f"\n[{label}]")
        try:
            resp = requests.get(BASE_URL, params=table["params"], timeout=15)
            data = resp.json()
            is_error = isinstance(data, dict) and "err" in data

            if is_error:
                total_skip += 1
                print(f"  SKIP: {data.get('errMsg', data)}")
                results[label] = {"error": data.get("errMsg", str(data))}
            else:
                rows = len(data) if isinstance(data, list) else 0
                total_ok += 1
                print(f"  OK: {rows} rows")
                results[label] = {"row_count": rows, "data": data}

        except Exception as exc:
            total_err += 1
            print(f"  ERR: {exc}")
            results[label] = {"error": str(exc)}

        time.sleep(0.5)

    results["_summary"] = {"ok": total_ok, "skip": total_skip, "err": total_err}
    return results

def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results = collect()
    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved -> {OUTPUT_PATH}")
    print(f"Summary: ok={results['_summary']['ok']} skip={results['_summary']['skip']} err={results['_summary']['err']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
