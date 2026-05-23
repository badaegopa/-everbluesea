#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재설계 변수 6종 API 가용성 프로브. 결과를 fetch_redesign_report.md 로 저장."""
import os, json, datetime, requests

KOSIS_KEY     = os.environ.get("KOSIS_API_KEY", "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
ECOS_KEY      = os.environ.get("ECOS_API_KEY", "")
DATA_GO_KR_KEY= os.environ.get("DATA_GO_KR_API_KEY", os.environ.get("NKIS_API_KEY", ""))

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ULSAN_SGG  = "31110 31140 31170 31200 31710"   # 중/남/동/북/울주 (31계열)
ULSAN_SGG26 = "26010 26020 26030 26040 26310"  # e-지방지표 등 26계열 (중/남/동/북/울주)
TIMEOUT = 20

def kosis_probe(tbl, itm="ALL", obj=ULSAN_SGG, org="101", prd="Y", n="1", extra=None):
    p = {"method":"getList","apiKey":KOSIS_KEY,"format":"json","jsonVD":"Y",
         "orgId":org,"tblId":tbl,"itmId":itm,"objL1":obj,"prdSe":prd,"newEstPrdCnt":n}
    if extra: p.update(extra)
    try:
        r = requests.get(KOSIS_BASE, params=p, timeout=TIMEOUT)
        try: data = r.json()
        except Exception: return {"http":r.status_code,"ok":False,"note":"non-JSON","raw":r.text[:200]}
        if isinstance(data, dict) and "err" in data:
            return {"http":r.status_code,"ok":False,"err":data.get("err"),"errMsg":data.get("errMsg","")[:120]}
        if isinstance(data, list):
            sample = data[0] if data else {}
            return {"http":r.status_code,"ok":True,"rows":len(data),
                    "sample":{k:sample.get(k) for k in ("C1_NM","ITM_NM","PRD_DE","DT","UNIT_NM") if k in sample}}
        return {"http":r.status_code,"ok":False,"note":"unexpected","raw":str(data)[:200]}
    except Exception as e:
        return {"ok":False,"exc":str(e)[:160]}

def ecos_probe(stat_code, cycle="A", start="2020", end="2025"):
    if not ECOS_KEY:
        return {"ok":False,"skip":"ECOS_API_KEY 미설정","need":"ecos.bok.or.kr 발급키 필요"}
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/10/{stat_code}/{cycle}/{start}/{end}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        d = r.json()
        if "StatisticSearch" in d:
            info = d["StatisticSearch"]
            row = (info.get("row") or [{}])[0]
            return {"http":r.status_code,"ok":True,"total":info.get("list_total_count"),
                    "scope":"전국(구군 분해 없음)",
                    "sample":{"stat":row.get("STAT_NAME"),"item":row.get("ITEM_NAME1"),
                              "time":row.get("TIME"),"value":row.get("DATA_VALUE"),"unit":row.get("UNIT_NAME")}}
        err = d.get("RESULT", d)
        return {"http":r.status_code,"ok":False,"err":str(err)[:160]}
    except Exception as e:
        return {"ok":False,"exc":str(e)[:160]}

def datago_probe(name):
    if not DATA_GO_KR_KEY:
        return {"ok":False,"skip":"DATA_GO_KR_API_KEY 미설정","need":"data.go.kr 소방청 활용신청·승인 필요"}
    return {"ok":None,"note":f"키 보유({name}) — 엔드포인트 URL 확정 후 호출 필요"}

PROBES = [
    # 통계표는 존재하나 objL 분류구조(objL1+objL2 추정) 미해결 → 메타조회 필요
    ("① 인구순이동률",  "KOSIS DT_1B26A01", lambda: kosis_probe("DT_1B26A01", prd="M")),
    # 사용자 제시 DT_1YL20711 → 오류. 정정 코드 DT_1YL20921 + 울산 26계열 필터
    ("② 재정자립도",    "KOSIS DT_1YL20921(정정) 울산5구군",
        lambda: kosis_probe("DT_1YL20921", obj=ULSAN_SGG26)),
    # ✅ 가용 (단 시도단위 — 구군 분해 불가)
    ("③ 1인당 GRDP",   "KOSIS 지역소득 DT_1C86", lambda: kosis_probe("DT_1C86", obj="31", prd="Y")),
    # 후보 코드 모두 부적합(1JU1505/1JU1517=없음, 1IN1502=총인구) → 정확 tblId 필요
    ("④ 빈집률",        "KOSIS 주택총조사 (코드 미확정)", lambda: kosis_probe("DT_1JU1505")),
    ("⑤ 응급 골든타임", "data.go.kr 소방청", lambda: datago_probe("소방청 구급")),
    ("⑥ 가계부채",      "ECOS 가계신용 151Y001", lambda: ecos_probe("151Y001")),
]

def main():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    results = []
    print(f"재설계 변수 API 프로브: {now}")
    for label, src, fn in PROBES:
        print(f"  [{label}] {src} ...", end=" ", flush=True)
        res = fn()
        print("OK" if res.get("ok") else ("SKIP" if res.get("skip") else "FAIL"))
        results.append((label, src, res))

    lines = [f"# 재설계 변수 API 수집 테스트 리포트", "",
             f"- 생성: {now}",
             f"- KOSIS 키: {'보유' if KOSIS_KEY else '없음'} / ECOS 키: {'보유' if ECOS_KEY else '없음'} / data.go.kr 키: {'보유' if DATA_GO_KR_KEY else '없음'}",
             f"- 울산 5구군 코드: {ULSAN_SGG}", "",
             "## 항목별 가용성", ""]
    for label, src, res in results:
        if res.get("ok") is True:
            status = "✅ 가용"
        elif res.get("ok") is None:
            status = "🟡 부분(키만 보유)"
        elif res.get("skip"):
            status = "⚪ 키 미설정"
        else:
            status = "❌ 실패"
        lines.append(f"### {label}")
        lines.append(f"- 소스: `{src}`")
        lines.append(f"- 상태: **{status}**")
        lines.append(f"- 응답: `{json.dumps(res, ensure_ascii=False)}`")
        lines.append("")

    okc  = sum(1 for _,_,r in results if r.get("ok") is True)
    lines += ["## 요약", "",
              f"- ✅ 즉시 가용: {okc}/6",
              "- 🟡/⚪ 키 발급 필요: ECOS(ecos.bok.or.kr), data.go.kr 소방청 활용신청",
              "- ③④ KOSIS tblId는 후보값 — 실패 시 통계표 코드 재확인 필요", ""]

    out = "fetch_redesign_report.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n저장: {out} (✅ {okc}/6 가용)")

if __name__ == "__main__":
    main()
