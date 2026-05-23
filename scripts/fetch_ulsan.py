"""DURE-η 파이프라인 v2 확정판"""
from __future__ import annotations
import json, sys, time, os
from pathlib import Path
import requests

KOSIS_KEY   = os.environ.get("KOSIS_API_KEY",        "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
SGIS_KEY    = os.environ.get("SGIS_CONSUMER_KEY",    "a7f9a200a67241698800")
SGIS_SECRET = os.environ.get("SGIS_CONSUMER_SECRET", "7509589f1d3142d586b2")
OUTPUT      = Path("data/ulsan.json")
OUTPUT_L12  = Path("data/lambda12.json")
BASE        = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
# ⚠️ 표마다 울산 구군 코드체계가 다름 (메타 검증 완료):
#   - 인구  DT_1B040A3 : 31 계열 (중31110/남31140/동31170/북31200/울주31710)
#   - 출산율 DT_1B81A17 : 26 계열 (중26010/남26020/동26030/북26040/울주26310) — 31계열은 경기도!
GU_CODES    = "31110 31140 31170 31200 31710"   # 인구표(DT_1B040A3)
BIRTH_CODES = "26010 26020 26030 26040 26310"   # 출산율표(DT_1B81A17) · 재정자립도(DT_1YL20921) 동일
CENSUS_CODES= "26010 26020 26030 26040 26510"   # 인구주택총조사(빈집·총주택) — ★울주군=26510

# ── Λ¹² 12변수 가중치 (합=1.00) ─────────────────────────────────
LAMBDA12_WEIGHTS = {
    "P1": 0.10, "P2": 0.10, "A1": 0.05, "A2": 0.10,
    "E1": 0.10, "E2": 0.10, "S1": 0.10, "S2": 0.05,
    "G1": 0.05, "G2": 0.05, "C1": 0.10, "C2": 0.10,
}
# 정규화 앵커 (lo, hi, invert, 설명). risk=clamp((v-lo)/(hi-lo)); invert면 1-risk.
# invert=True = 값이 낮을수록 위험(역지표). 실제 관측 범위 기반(조정 가능).
LAMBDA12_NORM = {
    "P1": (-2.0, 2.0, True, "순이동률%(역) 높을수록 유입=좋음 — 구군별 슬롯 대체(①)"),
    "P2": (0,   500,   False, "노사분규 건수"),
    "A2": (200000, 600000, False, "분기 범죄건수"),
    "E1": (0.50, 0.68, False, "지니계수"),
    "E2": (2.0,  15.0, False, "청년실업률%"),
    "S1": (0.6,  1.8,  True,  "합계출산율(역)"),
    "S2": (80.0, 99.0, True,  "인터넷이용률%(역)"),
    "G1": (300000, 800000, False, "국방예산억원"),
    "G2": (10.0, 50.0, True,  "재정자립도%(역) — 구군별 슬롯 대체(②)"),
    "C1": (1.0,  4.0,  True,  "천명당 의사수(역)"),
    "C2": (3.0,  15.0, False, "빈집률%(높을수록 위험) — 구군별 슬롯 대체(④)"),
    # S1 구별 결합용 고령비율 앵커(가중치 키 아님 — S1 risk = mean(TFR역, 고령)).
    "S1_aged": (10.0, 25.0, False, "고령인구비율%(높을수록 인구압력↑)"),
}
A1_FIXED = 0.5   # 엘리트결속: 국회 API 미연결 → fallback 고정

TABLES = [
    {"label":"울산_구군별_인구",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1B040A3","itmId":"T20 T21 T22",
               "objL1":GU_CODES,"prdSe":"M","newEstPrdCnt":"3"}},
    {"label":"울산_구군별_출산율",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1B81A17","itmId":"T1",
               "objL1":BIRTH_CODES,"prdSe":"Y","newEstPrdCnt":"3"}},
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
    # ① 순이동 → P1 슬롯 (31계열, 1인이동건수 T25, 성0·연령000 계). 순이동률=건수/인구×100
    {"label":"울산_순이동",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1B26A01","itmId":"T25",
               "objL1":GU_CODES,"objL2":"0","objL3":"000","prdSe":"M","newEstPrdCnt":"1"}},
    # ② 재정자립도 → G2 슬롯 (26계열, 개편전/후 2항목 → 추출시 개편전 우선)
    {"label":"울산_재정자립도",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1YL20921","itmId":"ALL",
               "objL1":BIRTH_CODES,"prdSe":"Y","newEstPrdCnt":"1"}},
    # ④ 빈집률 → C2 슬롯 (census 26계열, 빈집호수 / 총주택)
    {"label":"울산_빈집",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1JU1512","itmId":"T000",
               "objL1":CENSUS_CODES,"objL2":"00","prdSe":"Y","newEstPrdCnt":"1"}},
    {"label":"울산_총주택",
     "params":{"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
               "orgId":"101","tblId":"DT_1JU1501","itmId":"T10",
               "objL1":CENSUS_CODES,"prdSe":"Y","newEstPrdCnt":"1"}},
]
CENSUS2GU = {"26010":"31110","26020":"31140","26030":"31170","26040":"31200","26510":"31710"}

# 캐노니컬 키(인구표 31코드) → 이름·색상 + 출산율표 26코드 매핑
GU = {
    "31110":{"name":"중구",  "color":"#9A6800", "birth":"26010"},
    "31140":{"name":"남구",  "color":"#3A6A5E", "birth":"26020"},
    "31170":{"name":"동구",  "color":"#C73E1D", "birth":"26030"},
    "31200":{"name":"북구",  "color":"#185FA5", "birth":"26040"},
    "31710":{"name":"울주군","color":"#5A5650", "birth":"26310"},
}
BIRTH2GU = {v["birth"]: code for code, v in GU.items()}   # 26코드 → 31캐노니컬

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
    url = f"https://sgisapi.kostat.go.kr/OpenAPI3/boundary/hadmarea.geojson?accessToken={token}&year=2023&adm_cd=31&low_search=1"
    r = requests.get(url, timeout=15)
    d = r.json()
    if d.get("errCd") == 0:
        print(f"  SGIS boundary OK: {len(d.get('features',[]))} features")
        return d
    print(f"  SGIS boundary FAIL: {d.get('errMsg')}")
    return None

def load_lambda12():
    """data/lambda12.json 읽기. 없으면 fetch_lambda12 모듈로 직접 수집 후 저장."""
    if OUTPUT_L12.exists():
        print(f"  lambda12.json 로드: {OUTPUT_L12}")
        return json.loads(OUTPUT_L12.read_text(encoding="utf-8"))
    print("  lambda12.json 없음 → KOSIS 직접 수집")
    import fetch_lambda12 as L12   # scripts/ 가 sys.path[0]
    kosis = L12.collect_kosis(L12.LAMBDA12_TABLES)
    summary = L12.summarize(kosis)
    a1 = L12.collect_a1()
    data = {"summary": summary, "kosis": kosis,
            "A1": {"value": a1["value"], "source": a1["source"],
                   "unit": a1["unit"], "fallback": a1.get("fallback", False)}}
    OUTPUT_L12.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_L12.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def lambda12_values(l12):
    """lambda12.json → {var: float}. KOSIS 변수는 summary 최신값, A1은 별도 필드."""
    vals = {}
    sm = l12.get("summary", {})
    # S1 은 합계출산율(S1_tfr)을 대표값으로 사용
    # P1(순이동률)·G2(재정자립도)·C2(빈집률)는 구군별 슬롯으로 대체 → 공통값 제외(calc_eta에서 구군별 주입)
    keymap = {"P2": "P2", "A2": "A2", "E1": "E1", "E2": "E2",
              "S1": "S1_tfr", "S2": "S2", "G1": "G1", "C1": "C1"}
    for var, skey in keymap.items():
        node = sm.get(skey, {})
        lt = node.get("latest") if isinstance(node, dict) else None
        try:
            vals[var] = float(lt["value"]) if lt and lt.get("value") not in (None, "", "-") else None
        except (TypeError, ValueError):
            vals[var] = None
    vals["A1"] = l12.get("A1", {}).get("value", A1_FIXED)
    return vals


def norm(var, v):
    """값 v → 0~1 위험점수 (LAMBDA12_NORM 앵커, invert 반영). v=None 이면 None."""
    if v is None:
        return None
    lo, hi, invert, _ = LAMBDA12_NORM[var]
    r = (v - lo) / (hi - lo)
    r = min(max(r, 0.0), 1.0)
    return round(1.0 - r, 4) if invert else round(r, 4)


def l12_per_gu(l12, var, itm):
    """lambda12.json 의 var 블록에서 itm 항목을 구군별(26코드→31캐노니컬) 최신값으로 추출."""
    out = {}
    block = next((b for b in l12.get("kosis", {}).values() if b.get("var") == var), None)
    if not block:
        return out
    seen = set()
    for row in sorted(block.get("data", []), key=lambda x: x.get("PRD_DE", ""), reverse=True):
        if row.get("ITM_ID") != itm:
            continue
        code = BIRTH2GU.get(row.get("C1", ""))
        if code and code not in seen:
            try: out[code] = float(row["DT"]); seen.add(code)
            except (TypeError, ValueError): pass
    return out


def calc_eta(kosis, l12):
    """Λ¹² 12변수 가중합 η. 구군별 차등: P1(①순이동률) · S1(출산율+고령) · C1(의사수) · G2(②재정자립도) · C2(④빈집률).
    나머지는 울산/전국 공통. S1 risk = mean(norm(S1,출산율역), norm(S1_AGED,고령)). A1 은 fallback 0.5 고정."""
    vals = lambda12_values(l12)

    # 구군별 인구 (표시용)
    pop = {}
    for row in kosis.get("울산_구군별_인구", {}).get("data", []):
        c1 = row.get("C1", "")
        if c1 in GU and row.get("ITM_NM") == "총인구수":
            try: pop[c1] = int(row["DT"])
            except: pass

    # 구군별 합계출산율 (최신 연도). 출산율표는 26코드 → 31캐노니컬로 변환.
    birth = {}
    seen = set()
    for row in sorted(kosis.get("울산_구군별_출산율", {}).get("data", []),
                      key=lambda x: x.get("PRD_DE", ""), reverse=True):
        code = BIRTH2GU.get(row.get("C1", ""))
        if code and code not in seen:
            try: birth[code] = float(row["DT"]); seen.add(code)
            except: pass

    # 구군별 고령비율(T10 = A÷B×100) · 천명당 의사수(T10) — lambda12.json 에서
    aged    = l12_per_gu(l12, "S1_aged", "T10")
    doctors = l12_per_gu(l12, "C1", "T10")

    # ① 순이동률 → P1 (31계열, 순이동 건수 / 인구 × 100)
    migr = {}
    for row in kosis.get("울산_순이동", {}).get("data", []):
        code = row.get("C1", "")
        if code in GU:
            try: migr[code] = float(row["DT"])
            except (TypeError, ValueError): pass
    mig_rate = {c: round(migr[c] / pop[c] * 100, 3)
                for c in migr if pop.get(c)}

    # ② 재정자립도 → G2 (26계열, 세입과목개편전 우선)
    fiscal = {}
    for row in kosis.get("울산_재정자립도", {}).get("data", []):
        code = BIRTH2GU.get(row.get("C1", ""))
        if not code:
            continue
        if code not in fiscal or "개편전" in (row.get("ITM_NM") or ""):
            try: fiscal[code] = float(row["DT"])
            except (TypeError, ValueError): pass

    # ④ 빈집률 → C2 (census 26계열: 빈집호수 / 총주택 × 100)
    vac_h, tot_h = {}, {}
    for row in kosis.get("울산_빈집", {}).get("data", []):
        code = CENSUS2GU.get(row.get("C1", ""))
        if code:
            try: vac_h[code] = float(row["DT"])
            except (TypeError, ValueError): pass
    for row in kosis.get("울산_총주택", {}).get("data", []):
        code = CENSUS2GU.get(row.get("C1", ""))
        if code:
            try: tot_h[code] = float(row["DT"])
            except (TypeError, ValueError): pass
    vacancy = {c: round(vac_h[c] / tot_h[c] * 100, 2)
               for c in vac_h if tot_h.get(c)}

    # 공통(전국/울산) 변수 위험점수 — A1 은 고정값 그대로 사용
    common_risk = {var: (vals["A1"] if var == "A1" else norm(var, vals.get(var)))
                   for var in LAMBDA12_WEIGHTS}

    eta = {}
    for code, info in GU.items():
        risk = dict(common_risk)
        # S1(인구압력) = 출산율 위험 + 고령 위험 평균 (구군별)
        s1_parts = [r for r in (norm("S1", birth.get(code)),
                                norm("S1_aged", aged.get(code))) if r is not None]
        if s1_parts:
            risk["S1"] = round(sum(s1_parts) / len(s1_parts), 4)
        # C1(공공서비스) 구군별 의사수
        if doctors.get(code) is not None:
            risk["C1"] = norm("C1", doctors[code])
        # P1(①순이동률) · G2(②재정자립도) · C2(④빈집률) 구군별 슬롯 대체
        if mig_rate.get(code) is not None:
            risk["P1"] = norm("P1", mig_rate[code])
        if fiscal.get(code) is not None:
            risk["G2"] = norm("G2", fiscal[code])
        if vacancy.get(code) is not None:
            risk["C2"] = norm("C2", vacancy[code])

        score = wsm = 0.0
        for var, w in LAMBDA12_WEIGHTS.items():
            if risk[var] is not None:
                score += risk[var] * w
                wsm   += w

        eta[code] = {
            "name":   info["name"],
            "color":  info["color"],
            "pop":    pop.get(code, 0),
            "tfr":    birth.get(code),
            "aged":   aged.get(code),
            "doctors": doctors.get(code),
            "net_migration_rate":  mig_rate.get(code),  # ① P1 슬롯
            "fiscal_independence": fiscal.get(code),   # ② G2 슬롯
            "vacancy_rate":        vacancy.get(code),   # ④ C2 슬롯
            "eta":    round(1 - score / wsm, 3) if wsm > 0 else None,  # risk→건강 극성 (η↑=양호)
            "lambda12": {var: risk[var] for var in LAMBDA12_WEIGHTS},
            "data_quality": f"{int(round(wsm * 100))}%",
        }
    return eta, {"raw_values": vals, "common_risk": common_risk, "weights": LAMBDA12_WEIGHTS}

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
    result["sgis"] = {"boundary": sgis_boundary(tok), "adm_cd":"31","year":"2023"} if tok else {"error":"token 실패"}

    print("\n[3] Λ¹² 12변수 로드")
    l12 = load_lambda12()

    print("\n[4] Λ¹² η 계산 (12변수 가중합)")
    eta, l12_meta = calc_eta(kosis, l12)
    result["eta"] = eta
    result["lambda12"] = l12_meta
    rv = l12_meta["raw_values"]
    print("  공통값: " + " ".join(f"{k}={rv[k]}" for k in LAMBDA12_WEIGHTS if rv.get(k) is not None))
    for code, v in eta.items():
        print(f"  {v['name']:4s}: η={v['eta']} | tfr={v['tfr']} pop={v['pop']} (품질 {v['data_quality']})")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 저장 → {OUTPUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
