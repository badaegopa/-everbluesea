#!/usr/bin/env python3
"""
fetch_lambda12.py — Λ¹² 12변수 KOSIS 데이터 수집
두레에타 (DURE-η) 프로젝트 · 늘푸른바다 사회동역학 연구소

기능:
1. Λ¹² 변수별 KOSIS 통계표(tblId) 수집 (statisticsParameterData.do)
2. 표마다 raw 응답 보존 + 변수별 최신값 요약 추출
3. data/lambda12.json 으로 저장

fetch_ulsan.py 통합 메모:
- KOSIS_KEY / collect_kosis() / TABLES 스키마를 fetch_ulsan.py와 동일하게 맞춤.
- 통합 시 LAMBDA12_TABLES 의 dict 들을 fetch_ulsan.py의 TABLES 리스트에 그대로 append 가능.
"""
from __future__ import annotations
import json, sys, time, os
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

# ── 설정 ──────────────────────────────────────────────────────────
KOSIS_KEY    = os.environ.get("KOSIS_API_KEY", "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
DATA_GO_KR_KEY = os.environ.get("DATA_GO_KR_API_KEY", "")   # GitHub Secrets / CI 에서 주입
OUTPUT       = Path("data/lambda12.json")
BASE         = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
# A1(엘리트결속): 국회 의안정보 BillInfoService2 — 법안 처리율(가결/전체처리)
BILL_API     = "http://apis.data.go.kr/9710000/BillInfoService2/getBillInfoList"
A1_FALLBACK  = 0.5   # 수집 실패 시 중립값

# ⚠️ 울산 행정구역코드: KOSIS 기준 시도=31 (44는 충청남도이므로 사용 금지).
#    fetch_ulsan.py 도 동일하게 31 계열을 사용한다. 필요 시 여기만 바꾸면 전체 반영됨.
ULSAN_SIDO = "31"
ULSAN_GU   = "31110 31120 31140 31170 31710"   # 중/남/동/북구·울주군 (인구동향·e지방지표 B코드 계열)
# ⚠️ 표마다 울산 코드체계가 다름:
#   - 노사분규(DT_11826_N004): 울산=05 (자체코드)
#   - 의사수 e-지방지표(DT_1YL20981): 울산시=26, 구군=26010~26310 (e지방 순번코드)
#   - 인터넷이용률(DT_1YL202101E): 울산=A0907
ULSAN_SGG  = "26010 26020 26030 26040 26310"   # 중/남/동/북구·울주군 (DT_1YL20981 전용)

# 최근 몇 개 기간을 받을지 (연/월 공통)
RECENT_N = "3"

# ── Λ¹² 변수 → KOSIS 통계표 매핑 ──────────────────────────────────
# scope: national=전국만, sido=시도단위(울산 필터), sigungu=시군구(울산 구군 필터), nationwide_count=전국 건수
# itmId / objL 미검증분은 "ALL" 로 전량 수집 후 파싱 (분류코드는 statisticsParameterData 메타로 추후 확정).
LAMBDA12_TABLES = [
    {"var": "E2", "label": "청년실업률(15-29세)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1DA7105S", "itmId": "T80",
                "objL1": "75", "objL2": "00", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "T80=실업률, objL1=75(15-29세), objL2=00(교육정도 계). 전국 표 — 울산 분해 불가(시도별은 DT_1DA7107S)."},

    {"var": "E1", "label": "지니계수(소득분배)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1HDAAD04", "itmId": "ALL",
                "objL1": "ALL", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "가계금융복지조사·순자산 지니계수(전국)."},

    {"var": "S1_tfr", "label": "합계출산율(시군구)", "scope": "sigungu",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1B81A17", "itmId": "T1",
                "objL1": "26010 26020 26030 26040 26310", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "⚠️ 이 표에서 울산은 26계열(중26010..울주26310). 31계열은 경기도이므로 사용 금지."},

    {"var": "S1_aged", "label": "고령인구비율(시군구)", "scope": "sigungu",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1YL20631", "itmId": "ALL",
                "objL1": "26010 26020 26030 26040 26310", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "e-지방지표 고령인구비율(65세+). ⚠️ 울산은 26계열(31계열은 경기도)."},

    {"var": "A2", "label": "범죄발생(전국)", "scope": "nationwide_count",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "132", "tblId": "DT_13204_A0400", "itmId": "T001",
                "objL1": "01", "prdSe": "Q", "newEstPrdCnt": "8"},
     "note": "DT_132004_A002는 전 칸 '-'(빈 표)라 폐기. DT_13204_A0400(전국)=실데이터, 분기전용. "
             "T001=발생건수, objL1=01(죄종 총계). 연간 범죄발생률=4개분기 합산÷인구×10만. 울산청은 DT_13204_A0407."},

    {"var": "G2", "label": "수출액(국가별)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "360", "tblId": "DT_1R11006_FRM101", "itmId": "ALL",
                "objL1": "ALL", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "무역통계 국가별 수출·수입액. 수출증가율은 전년대비 계산 필요."},

    {"var": "C2", "label": "초미세먼지 PM2.5(도시별)", "scope": "sido",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "106", "tblId": "DT_106N_03_0200145", "itmId": "ALL",
                "objL1": "ALL", "prdSe": "M", "newEstPrdCnt": "12"},
     "note": "월별 도시별 PM2.5. 연평균은 12개월 평균으로 산출(그래서 12개월 수집)."},

    {"var": "P2", "label": "노사분규 건수(시도별)", "scope": "sido",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "118", "tblId": "DT_11826_N004", "itmId": "01",
                "objL1": "01 05", "objL2": "100", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "01=노사분규건수, objL1=01(전국계)+05(울산 — 이 표 자체코드, 31 아님), objL2=100(반기 계)."},

    {"var": "P1", "label": "삶에 대한 만족도(민중분노 역지표)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "417", "tblId": "DT_417001_0002", "itmId": "T1",
                "objL1": "10", "objL2": "A12", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "사회통합실태조사. T1=만족도, objL1=10(전체), objL2=A12(평균/10점). 역방향(만족↓=분노↑)."},

    {"var": "S2", "label": "인터넷이용률(정보접근, 울산)", "scope": "sido",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1YL202101E", "itmId": "13103112704T1",
                "objL1": "A0907", "objL2": "13102112704B.002", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "인터넷이용실태조사. objL1=A0907(울산), objL2=...B.002(이용). 언론자유는 KOSIS 미수록."},

    {"var": "G1", "label": "국방예산(지정학리스크)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "122", "tblId": "DT_122009_001", "itmId": "T001",
                "objL1": "A0201", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "국방통계. objL1=A0201(국방비 총액). ODA 대안: 170 TX_10202_A000."},

    {"var": "C1", "label": "인구 천명당 의사수(공공서비스, 울산)", "scope": "sigungu",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1YL20981", "itmId": "T10",
                "objL1": ULSAN_SGG, "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "e-지방지표. T10=천명당 의사수(비율 직접 제공), objL1=울산 5구군(26계열)."},
]

# Λ¹² 12변수 중 KOSIS 미매핑(추후 보완) — 기록용
# A1(엘리트결속)은 KOSIS 미대응 → 국회 의안정보 BillInfoService2(data.go.kr)로 별도 수집(collect_a1).
# → Λ¹² 12변수 전부 라이브 수집(KOSIS 11 + 국회API 1).
LAMBDA12_UNMAPPED = []


def collect_kosis(tables):
    """fetch_ulsan.py와 동일한 반환 스키마: {label: {row_count, data} | {error}}"""
    results = {}
    for t in tables:
        label = t["label"]
        print(f"  [{t['var']:>7}] {label}", end=" ")
        try:
            r = requests.get(BASE, params=t["params"], timeout=20)
            data = r.json()
            if isinstance(data, dict) and "err" in data:
                print(f"SKIP err={data.get('err')} {data.get('errMsg', '')[:30]}")
                results[label] = {"var": t["var"], "tblId": t["params"]["tblId"],
                                  "error": data.get("errMsg")}
            else:
                rows = len(data) if isinstance(data, list) else 0
                print(f"OK {rows}행")
                results[label] = {"var": t["var"], "tblId": t["params"]["tblId"],
                                  "scope": t["scope"], "note": t.get("note", ""),
                                  "row_count": rows, "data": data}
        except Exception as e:
            print(f"ERR {e}")
            results[label] = {"var": t["var"], "tblId": t["params"]["tblId"], "error": str(e)}
        time.sleep(0.5)
    return results


def collect_a1(age="22", max_rows=1000):
    """A1(엘리트결속) = 국회 법안 처리율 = 가결건수 / 전체처리건수.
    국회 의안정보 BillInfoService2(getBillInfoList) XML 파싱. 정치 해석 없이 수치만.
    실패(키없음/네트워크/파싱) 시 A1_FALLBACK(0.5) 반환.
    - 분모(전체처리): procResultCd 가 채워진 건(=처리 완료된 법안)
    - 분자(가결):     procResultCd == "2" (또는 결과문구에 '가결' 포함)
    """
    out = {"var": "A1", "label": "법안처리율(엘리트결속)", "source": "국회의안정보API",
           "unit": "법안처리율", "endpoint": BILL_API}
    if not DATA_GO_KR_KEY:
        print("  [     A1] DATA_GO_KR_API_KEY 없음 → fallback")
        out.update({"value": A1_FALLBACK, "fallback": True, "note": "키 미설정(로컬). CI에서 secret 주입 필요."})
        return out
    print("  [     A1] 국회 의안정보API", end=" ")
    try:
        params = {"serviceKey": DATA_GO_KR_KEY, "numOfRows": str(max_rows), "pageNo": "1", "AGE": age}
        r = requests.get(BILL_API, params=params, timeout=25)
        root = ET.fromstring(r.text)
        # data.go.kr 표준 에러 봉투 점검
        code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
        if code not in (None, "00", "0"):
            raise RuntimeError(f"API resultCode={code} {root.findtext('.//resultMsg') or root.findtext('.//returnAuthMsg')}")
        proc_total = passed = 0
        for it in root.iter("item"):
            res_cd = (it.findtext("procResultCd") or it.findtext("PROC_RESULT_CD") or "").strip()
            res_tx = (it.findtext("generalResult") or it.findtext("procResult") or "").strip()
            if res_cd or res_tx:                       # 처리 완료된 법안
                proc_total += 1
                if res_cd == "2" or "가결" in res_tx:
                    passed += 1
        if proc_total == 0:
            raise RuntimeError("처리 완료 법안 0건(필드명/AGE 확인 필요)")
        val = round(passed / proc_total, 4)
        print(f"OK 가결 {passed}/{proc_total} = {val}")
        out.update({"value": val, "passed": passed, "proc_total": proc_total, "age": age, "fallback": False})
    except Exception as e:
        print(f"ERR {e} → fallback")
        out.update({"value": A1_FALLBACK, "fallback": True, "note": f"수집실패: {e}"})
    return out


def summarize(kosis):
    """변수별 최신값(가장 최근 PRD_DE의 DT) 한 줄 요약 — 데이터 가용성 점검용."""
    summary = {}
    for label, blk in kosis.items():
        var = blk.get("var", "?")
        if "error" in blk:
            summary[var] = {"label": label, "status": "error", "msg": blk["error"]}
            continue
        rows = blk.get("data", []) or []
        latest = None
        for row in sorted(rows, key=lambda x: x.get("PRD_DE", ""), reverse=True):
            dt = row.get("DT")
            if dt not in (None, "", "-"):
                latest = {"prd": row.get("PRD_DE"), "value": dt,
                          "item": row.get("ITM_NM"), "c1": row.get("C1_NM") or row.get("C1")}
                break
        summary[var] = {"label": label, "status": "ok", "rows": blk.get("row_count", 0),
                        "latest": latest}
    return summary


def main():
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print("=" * 56)
    print(f"Λ¹² 12변수 KOSIS 수집: {now}")
    print("=" * 56)

    print(f"\n[1] KOSIS ({len(LAMBDA12_TABLES)}개 변수)")
    kosis = collect_kosis(LAMBDA12_TABLES)

    print("\n[2] 변수별 최신값 요약")
    summary = summarize(kosis)
    for var, s in summary.items():
        if s["status"] == "error":
            print(f"  {var:>7}: ERROR {s['msg'][:40]}")
        else:
            lt = s["latest"]
            v = f"{lt['value']} ({lt['prd']}, {lt['item']})" if lt else "값 없음"
            print(f"  {var:>7}: {v}  [{s['rows']}행]")

    print("\n[3] A1 — 국회 법안처리율")
    a1 = collect_a1()
    summary["A1"] = {"label": a1["label"], "status": "fallback" if a1.get("fallback") else "ok",
                     "value": a1["value"], "source": a1["source"]}
    print(f"  A1 = {a1['value']} ({'fallback' if a1.get('fallback') else '실데이터'}, {a1['unit']})")

    result = {
        "_updated": now,
        "_unmapped": LAMBDA12_UNMAPPED,
        "_region": {"ulsan_sido": ULSAN_SIDO, "ulsan_gu": ULSAN_GU.split()},
        "summary": summary,
        "kosis": kosis,
        "A1": {"value": a1["value"], "source": a1["source"], "unit": a1["unit"],
               "fallback": a1.get("fallback", False), "detail": {k: a1[k] for k in
               ("passed", "proc_total", "age", "note") if k in a1}},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 저장 → {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
