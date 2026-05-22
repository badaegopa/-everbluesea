"""DURE-η 파이프라인 v2 확정판"""
from __future__ import annotations
import json, sys, time, os
from pathlib import Path
import requests

KOSIS_KEY   = os.environ.get("KOSIS_API_KEY",        "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
SGIS_KEY    = os.environ.get("SGIS_CONSUMER_KEY",    "a7f9a200a67241698800")
SGIS_SECRET = os.environ.get("SGIS_CONSUMER_SECRET", "7509589f1d3142d586b2")
OUTPUT      = Path("data/ulsan.json")
BASE        = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
GU_CODES    = "31110 31120 31140 31170 31710"

TABLES = [
    {"label":"울산_구군별_인구",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1B040A3","itmId":"T20 T21 T22",
               "objL1":GU_CODES,"prdSe":"M","newEstPrdCnt":"3"}},
    {"label":"울산_구군별_출산율",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1B81A17","itmId":"T1",
               "objL1":GU_CODES,"prdSe":"Y","newEstPrdCnt":"3"}},
    {"label":"울산_고용현황",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1DA7004S","itmId":"ALL",
               "objL1":"31","prdSe":"Y","newEstPrdCnt":"3"}},
    {"label":"울산_기초수급",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1YL13801E","itmId":"ALL",
               "objL1":"31","prdSe":"Y","newEstPrdCnt":"3"}},
    {"label":"울산_노령화지수",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1YL12501E","itmId":"ALL",
               "objL1":"31","prdSe":"Y","newEstPrdCnt":"3"}},
]

GU = {
    "31110":{"name":"중구",  "color":"#9A6800"},
    "31120":{"name":"남구",  "color":"#3A6A5E"},
    "31140":{"name":"동구",  "color":"#C73E1D"},
    "31170":{"name":"북구",  "color":"#185FA5"},
    "31710":{"name":"울주군","color":"#5A5650"},
}

def collect_kosis():
    results = {}
    for t in TABLES:
        label = t["label"]
        print(f"  [{label}]", end=" ")
        try:
            r = requests.get(BASE, params=t["params"], timeout=15)
            data = r.json()
            if isinstance(data, dict) and "err" in data:
                print(f"SKIP err={data.get('err')} {data.get('errMsg','')[:30]}")
                results[label] = {"error": data.get("errMsg")}
            else:
                rows = len(data) if isinstance(data, list) else 0
                print(f"OK {rows}행")
                results[label] = {"row_count": rows, "data": data}
        except Exception as e:
            print(f"ERR {e}")
            results[label] = {"error": str(e)}
        time.sleep(0.5)
    return results

def sgis_token():
    url = f"https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.json?consumer_key={SGIS_KEY}&consumer_secret={SGIS_SECRET}"
    r = requests.get(url, timeout=10)
    d = r.json()
    if d.get("errCd") == 0:
        tok = d["result"]["accessToken"]
        print(f"  SGIS token OK: {tok[:8]}...")
        return tok
    print(f"  SGIS FAIL: {d}")
    return None

def sgis_boundary(token):
    url = f"https://sgisapi.kostat.go.kr/OpenAPI3/boundary/hadmarea.geojson?accessToken={token}&year=2023&adm_cd=26&low_search=1"
    r = requests.get(url, timeout=15)
    d = r.json()
    if d.get("errCd") == 0:
        print(f"  SGIS boundary OK: {len(d.get('features',[]))} features")
        return d
    print(f"  SGIS boundary FAIL: {d.get('errMsg')}")
    return None

def calc_eta(kosis):
    # 인구 파싱
    pop = {}
    for row in kosis.get("울산_구군별_인구",{}).get("data",[]):
        c1 = row.get("C1","")
        if c1 in GU and row.get("ITM_NM")=="총인구수":
            try: pop[c1] = int(row["DT"])
            except: pass

    # 출산율 파싱 (최신 연도)
    birth = {}
    seen = set()
    for row in sorted(kosis.get("울산_구군별_출산율",{}).get("data",[]),
                      key=lambda x: x.get("PRD_DE",""), reverse=True):
        c1 = row.get("C1","")
        if c1 in GU and c1 not in seen:
            try: birth[c1] = float(row["DT"]); seen.add(c1)
            except: pass

    # 고용률 파싱
    emp_rate = None
    for row in kosis.get("울산_고용현황",{}).get("data",[]):
        if row.get("ITM_NM") in ("고용률","고용률(%)"):
            try: emp_rate = float(row["DT"]); break
            except: pass

    # 기초수급자수 파싱
    welfare_total = None
    for row in kosis.get("울산_기초수급",{}).get("data",[]):
        try: welfare_total = int(row["DT"]); break
        except: pass

    # 노령화지수 파싱
    aging_idx = None
    for row in kosis.get("울산_노령화지수",{}).get("data",[]):
        try: aging_idx = float(row["DT"]); break
        except: pass

    ulsan_pop = sum(pop.values()) or 1
    welfare_rate = (welfare_total / ulsan_pop * 100) if welfare_total else None

    eta = {}
    for code, info in GU.items():
        p   = pop.get(code, 0)
        tfr = birth.get(code)
        score, wsm = 0.0, 0.0

        # 출산율 (낮을수록 위험: 0.6=1.0, 1.5=0.0) 가중 0.30
        if tfr is not None:
            score += min(max((1.5 - tfr) / 0.9, 0), 1.0) * 0.30
            wsm   += 0.30

        # 고용률 (낮을수록 위험: 55%=1.0, 70%=0.0) 가중 0.25
        if emp_rate is not None:
            score += min(max((70 - emp_rate) / 15, 0), 1.0) * 0.25
            wsm   += 0.25

        # 기초수급률 (높을수록 위험: 8%=1.0, 2%=0.0) 가중 0.25
        if welfare_rate is not None:
            score += min(max((welfare_rate - 2) / 6, 0), 1.0) * 0.25
            wsm   += 0.25

        # 노령화지수 (높을수록 위험: 500=1.0, 100=0.0) 가중 0.20
        if aging_idx is not None:
            score += min(max((aging_idx - 100) / 400, 0), 1.0) * 0.20
            wsm   += 0.20

        eta[code] = {
            "name":         info["name"],
            "color":        info["color"],
            "pop":          p,
            "tfr":          tfr,
            "emp_rate":     emp_rate,
            "welfare_rate": round(welfare_rate, 2) if welfare_rate else None,
            "aging_idx":    aging_idx,
            "eta":          round(score / wsm, 2) if wsm > 0 else None,
            "data_quality": f"{int(wsm * 100)}%",
        }
    return eta

def main():
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print("=" * 50)
    print(f"DURE-η 파이프라인 v2 확정: {now}")
    print("=" * 50)
    result = {"_updated": now}

    print("\n[1] KOSIS")
    kosis = collect_kosis()
    result["kosis"] = kosis

    print("\n[2] SGIS")
    tok = sgis_token()
    result["sgis"] = {"boundary": sgis_boundary(tok), "adm_cd":"26","year":"2023"} if tok else {"error":"token 실패"}

    print("\n[3] η 계산")
    result["eta"] = calc_eta(kosis)
    for code, v in result["eta"].items():
        print(f"  {v['name']:4s}: η={v['eta']} | tfr={v['tfr']} emp={v['emp_rate']} aging={v['aging_idx']} (품질 {v['data_quality']})")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 저장 → {OUTPUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
