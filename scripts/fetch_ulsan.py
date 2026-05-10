#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import requests

KST = timezone(timedelta(hours=9))

ULSAN_SGG = {
    "중구":   "31110",
    "남구":   "31140",
    "동구":   "31170",
    "북구":   "31200",
    "울주군": "31710",
}

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SGIS_AUTH  = "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.do"
SGIS_POPULATION = "https://sgisapi.kostat.go.kr/OpenAPI3/stats/population.json"

# 시군구별 주민등록인구 테이블 (objL1=ALL → 전체 시군구 받아서 울산만 필터)
KOSIS_TABLES = {
    "population": {"orgId":"101","tblId":"DT_1B040A3","itmId":"T20","objL1":"ALL","prdSe":"M","newEstPrdCnt":"1"},
    "employment": {"orgId":"101","tblId":"DT_1DA7002S","itmId":"ALL","objL1":"ALL","prdSe":"Y","newEstPrdCnt":"1"},
    "welfare":    {"orgId":"117","tblId":"DT_11761_N001","itmId":"ALL","objL1":"ALL","prdSe":"Y","newEstPrdCnt":"1"},
}

def env(name):
    v = os.environ.get(name)
    if not v:
        sys.stderr.write(f"[fatal] missing: {name}\n"); sys.exit(2)
    return v

def fetch_kosis(api_key, params):
    q = {"method":"getList","apiKey":api_key,"format":"json","jsonVD":"Y",**params}
    r = requests.get(KOSIS_BASE, params=q, timeout=30)
    r.raise_for_status()
    data = r.json()
    sys.stderr.write(f"[debug] kosis type={type(data).__name__} len={len(data) if isinstance(data,list) else 'n/a'} sample={str(data)[:200]}\n")
    return data

def filter_ulsan_rows(rows):
    if not isinstance(rows, list): return []
    out = []
    sgg_codes = set(ULSAN_SGG.values())
    sgg_names = set(ULSAN_SGG.keys())
    for row in rows:
        c1 = str(row.get("C1",""))
        c2 = str(row.get("C2",""))
        c1_nm = row.get("C1_NM","")
        # 5자리 시군구 코드 매칭 또는 구명 매칭
        if c1 in sgg_codes or c2 in sgg_codes or any(n in c1_nm for n in sgg_names):
            out.append(row)
    return out

def sgis_token(key, secret):
    sys.stderr.write(f"[debug] SGIS URL:{SGIS_AUTH}\n")
    r = requests.get(SGIS_AUTH,
                     params={"consumer_key":key,"consumer_secret":secret},
                     timeout=30,
                     headers={"Accept":"application/json"},
                     allow_redirects=False)
    sys.stderr.write(f"[debug] SGIS status={r.status_code}\n")
    if r.status_code in (301,302,303,307,308):
        loc = r.headers.get("Location","")
        sys.stderr.write(f"[debug] redirect → {loc}\n")
        r = requests.get(loc, timeout=30, headers={"Accept":"application/json"})
    r.raise_for_status()
    body = r.json()
    if body.get("errCd") not in (0,"0"):
        raise RuntimeError(f"SGIS auth failed: {body}")
    return body["result"]["accessToken"]

def fetch_sgis_population(token):
    out = {}
    for name, sgg in ULSAN_SGG.items():
        r = requests.get(SGIS_POPULATION,
                         params={"accessToken":token,"adm_cd":sgg,"low_search":"0"},
                         timeout=30,
                         headers={"Accept":"application/json"})
        try:
            r.raise_for_status(); out[name] = r.json()
        except Exception as e:
            out[name] = {"error": str(e)}
    return out

def main():
    kosis_key = env("KOSIS_API_KEY")
    sgis_key  = env("SGIS_CONSUMER_KEY")
    sgis_sec  = env("SGIS_CONSUMER_SECRET")

    payload = {
        "updated_at": datetime.now(KST).isoformat(),
        "region": "울산광역시",
        "districts": list(ULSAN_SGG.keys()),
        "sgg_codes": ULSAN_SGG,
        "kosis": {}, "sgis": {},
    }

    for category, params in KOSIS_TABLES.items():
        try:
            raw = fetch_kosis(kosis_key, params)
            ulsan_rows = filter_ulsan_rows(raw)
            payload["kosis"][category] = {
                "rows_total":  len(raw) if isinstance(raw,list) else 0,
                "ulsan_rows":  ulsan_rows,
                "ulsan_count": len(ulsan_rows),
            }
            sys.stderr.write(f"[ok] kosis/{category}: ulsan_count={len(ulsan_rows)}\n")
        except Exception as e:
            payload["kosis"][category] = {"error": str(e)}
            sys.stderr.write(f"[err] kosis/{category}: {e}\n")

    try:
        token = sgis_token(sgis_key, sgis_sec)
        sys.stderr.write("[ok] SGIS token OK\n")
        payload["sgis"]["population"] = fetch_sgis_population(token)
    except Exception as e:
        payload["sgis"]["population"] = {"error": str(e)}
        sys.stderr.write(f"[err] SGIS: {e}\n")

    out_path = Path(__file__).resolve().parent.parent / "data" / "ulsan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
