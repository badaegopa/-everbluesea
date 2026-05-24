#!/usr/bin/env python3
"""
fetch_national.py — Λ¹² 12변수 KOSIS 데이터 수집 (전국 단위)
두레에타 (DURE-η) 프로젝트 · 늘푸른바다 사회동역학 연구소

fetch_lambda12.py(울산/시군구판)의 전국판. 핵심 교훈:
  "전국" objL1 코드는 표 유형마다 전부 다르다 — 00을 일괄 가정하면 함정.
  실측값(2026-05-24, statisticsParameterData 메타 검증):
    인구류(출산율·고령·의사수) → 00
    경제류(지니)               → ALL(단일시리즈) / 수출 → 13102103829E.00(계)
    사회조사(사회통합)         → 10(전체, 지역축 없음)
    노사류(노사분규)           → 01(계, 자체순번)
    범죄(죄종축)               → 01(총계)
    국방(A코드)                → A0201(총액 = 국방예산 59.4조, A0101은 재정총액 449조라 오답)
    PM2.5 / 인터넷             → 13102128219A.4100001(총계) / 13102112704A.0000(전체) — 00 아님!

collect_kosis / summarize / collect_a1 은 fetch_lambda12.py 와 동일 스키마라 그대로 재사용.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

# scripts/ 가 sys.path[0] — 검증된 헬퍼 재사용
from fetch_lambda12 import KOSIS_KEY, collect_kosis, summarize, collect_a1, RECENT_N

OUTPUT = Path("data/national.json")

# ── Λ¹² 12변수 가중치 (합=1.00, fetch_ulsan.py LAMBDA12_WEIGHTS와 동일) ──
NATIONAL_WEIGHTS = {
    "P1": 0.10, "P2": 0.10, "A1": 0.05, "A2": 0.10,
    "E1": 0.10, "E2": 0.10, "S1": 0.10, "S2": 0.05,
    "G1": 0.05, "G2": 0.05, "C1": 0.10, "C2": 0.10,
}

# ── 전국 정규화 앵커 (lo, hi, invert) ──────────────────────────────
# ⚠️ fetch_ulsan.py 앵커와 다름: 거기선 P1/G2/C2가 구군 슬롯(순이동률/재정자립도/빈집률).
#    전국은 본래 의미 — P1=삶의 만족도, G2=수출증가율, C2=PM2.5 농도.
# risk = clamp((v-lo)/(hi-lo)); invert=True면 값 낮을수록 위험(역지표) → 1-risk.
NATIONAL_NORM = {
    "P1": (4.0, 8.0,  True,  "삶의 만족도(10점, 역: 만족↓=분노↑)"),
    "P2": (0,   300,  False, "노사분규 건수(높을수록 위험)"),
    "A2": (200000, 600000, False, "분기 범죄 발생건수"),
    "E1": (0.50, 0.68, False, "순자산 지니계수"),
    "E2": (2.0,  15.0, False, "청년실업률%"),
    "S1": (0.6,  1.8,  True,  "합계출산율(역)"),
    "S1_aged": (10.0, 25.0, False, "고령인구비율%(인구압력↑)"),
    "S2": (80.0, 99.0, True,  "인터넷이용률%(역: 접근↑=위험↓)"),
    "G1": (300000, 800000, False, "국방예산(억원)"),
    "G2": (-10.0, 20.0, True,  "수출증가율%(역: 증가=좋음)"),
    "C1": (1.0,  4.0,  True,  "인구 천명당 의사수(역)"),
    "C2": (5.0,  35.0, False, "PM2.5 연평균(㎍/㎥, 높을수록 위험)"),
}

# ── Λ¹² 12변수 → KOSIS 전국 통계표 매핑 (전국코드 전수 메타 검증 완료) ──
NATIONAL_TABLES = [
    {"var": "E2", "label": "청년실업률(15-29세)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1DA7105S", "itmId": "T80",
                "objL1": "75", "objL2": "00", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "objL1=연령축(75=15-29세 청년, 전연령계는 00). T80=실업률, objL2=00(교육 계)."},

    {"var": "E1", "label": "지니계수(순자산)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1HDAAD04", "itmId": "ALL",
                "objL1": "ALL", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "가계금융복지조사. C1=A01(순자산 지니) 단일시리즈라 ALL 무해. 소득 아닌 순자산 지니."},

    {"var": "S1_tfr", "label": "합계출산율(전국)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1B81A17", "itmId": "T1",
                "objL1": "00", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "⚠️ 전국=00 (시군구판은 26계열 울산). 2024 TFR=0.748 검증."},

    {"var": "S1_aged", "label": "고령인구비율(전국)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1YL20631", "itmId": "T10",
                "objL1": "00", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "e-지방지표. 전국=00, itm=T10(고령인구비율 A÷B×100). 2025=21.2%. T001/T002는 분자·분모."},

    {"var": "A2", "label": "범죄발생(전국)", "scope": "nationwide_count",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "132", "tblId": "DT_13204_A0400", "itmId": "T001",
                "objL1": "01", "prdSe": "Q", "newEstPrdCnt": "8"},
     "note": "objL1=죄종축(01=총계). T001=발생건수, 분기전용. 연 범죄율=4분기합÷인구×10만."},

    {"var": "G2", "label": "수출액(전국 계)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "360", "tblId": "DT_1R11006_FRM101", "itmId": "13103103829T1",
                "objL1": "13102103829E.00", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "⚠️ objL1=ALL은 248개국. 전국 계=13102103829E.00, itm=13103103829T1(수출액, 수입액 T2 차단). "
             "2025 $709B. 수출증가율은 전년대비 계산 필요."},

    {"var": "C2", "label": "초미세먼지 PM2.5(전국)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "106", "tblId": "DT_106N_03_0200145", "itmId": "13103128219T.1100001",
                "objL1": "13102128219A.4100001", "prdSe": "M", "newEstPrdCnt": "12"},
     "note": "⚠️ 전국=13102128219A.4100001(총계) — 00 아님. 월평균 itm. 연평균=12개월 평균(그래서 12개월 수집)."},

    {"var": "P2", "label": "노사분규 건수(전국)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "118", "tblId": "DT_11826_N004", "itmId": "01",
                "objL1": "01", "objL2": "100", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "전국=01(계, 자체순번 — 시도판은 05=울산). 01=노사분규건수, objL2=100(반기 계)."},

    {"var": "P1", "label": "삶에 대한 만족도(민중분노 역지표)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "417", "tblId": "DT_417001_0002", "itmId": "T1",
                "objL1": "10", "objL2": "A12", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "사회통합실태조사. objL1=응답자특성축(10=전체, 지역코드 없음). T1=만족도, objL2=A12(평균/10점). 역방향."},

    {"var": "S2", "label": "인터넷이용률(전국)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1YL202101E", "itmId": "13103112704T1",
                "objL1": "13102112704A.0000", "objL2": "13102112704B.002", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "⚠️ 전국=13102112704A.0000(전체) — 00 아님(시도판 A0907=울산). 2025=95%. objL2=...B.002(이용)."},

    {"var": "G1", "label": "국방예산(지정학리스크)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "122", "tblId": "DT_122009_001", "itmId": "T001",
                "objL1": "A0201", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "⚠️ A0201=총액(국방예산 59.4조). A0101도 '총액'이나 재정총액(449조)이라 오답."},

    {"var": "C1", "label": "인구 천명당 의사수(전국)", "scope": "national",
     "params": {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
                "orgId": "101", "tblId": "DT_1YL20981", "itmId": "T10",
                "objL1": "00", "prdSe": "Y", "newEstPrdCnt": RECENT_N},
     "note": "e-지방지표. 전국=00, T10=천명당 의사수(비율 직접 제공). 2025=3.3명."},
]


def norm(var, v):
    """값 v → 0~1 위험점수 (NATIONAL_NORM 앵커, invert 반영). v=None이면 None."""
    if v is None:
        return None
    lo, hi, invert, _ = NATIONAL_NORM[var]
    r = (v - lo) / (hi - lo)
    r = min(max(r, 0.0), 1.0)
    return round(1.0 - r, 4) if invert else round(r, 4)


def _block(kosis, var):
    return next((b for b in kosis.values() if b.get("var") == var and "data" in b), None)


def _latest(kosis, var, itm=None):
    """var 블록의 최신 PRD_DE DT(float). itm 지정 시 ITM_ID 필터."""
    blk = _block(kosis, var)
    if not blk:
        return None
    for row in sorted(blk["data"], key=lambda x: x.get("PRD_DE", ""), reverse=True):
        if itm and row.get("ITM_ID") != itm:
            continue
        dt = row.get("DT")
        if dt not in (None, "", "-"):
            try:
                return float(dt)
            except ValueError:
                return None
    return None


def calc_national_eta(kosis, a1_value):
    """전국 Λ¹² 12변수 가중합 η. risk→건강 극성(η↑=양호).
    대부분 최신값 직접 사용. 예외: G2=수출 전년대비 증가율, C2=PM2.5 12개월 이동평균,
    S1=출산율 역 + 고령 평균. A1=법안처리율(0~1)을 risk로 직접 사용(fetch_ulsan 동일)."""
    raw = {
        "P1": _latest(kosis, "P1"),
        "P2": _latest(kosis, "P2"),
        "A2": _latest(kosis, "A2"),
        "E1": _latest(kosis, "E1"),
        "E2": _latest(kosis, "E2"),
        "S1_tfr":  _latest(kosis, "S1_tfr"),
        "S1_aged": _latest(kosis, "S1_aged"),
        "S2": _latest(kosis, "S2"),
        "G1": _latest(kosis, "G1"),
        "C1": _latest(kosis, "C1"),
    }

    # G2 = 수출 전년대비 증가율% (최근 2개 연도)
    g2_blk = _block(kosis, "G2")
    g2_growth = None
    if g2_blk:
        yrs = {}
        for row in g2_blk["data"]:
            try:
                yrs[row["PRD_DE"]] = float(row["DT"])
            except (KeyError, TypeError, ValueError):
                pass
        if len(yrs) >= 2:
            ks = sorted(yrs)
            prev, cur = yrs[ks[-2]], yrs[ks[-1]]
            if prev:
                g2_growth = round((cur - prev) / prev * 100, 2)
    raw["G2"] = g2_growth

    # C2 = PM2.5 12개월 이동평균
    c2_blk = _block(kosis, "C2")
    c2_avg = None
    if c2_blk:
        vals = []
        for row in c2_blk["data"]:
            try:
                vals.append(float(row["DT"]))
            except (KeyError, TypeError, ValueError):
                pass
        if vals:
            c2_avg = round(sum(vals) / len(vals), 2)
    raw["C2"] = c2_avg

    # 변수별 위험점수
    risk = {
        "P1": norm("P1", raw["P1"]),
        "P2": norm("P2", raw["P2"]),
        "A1": round(a1_value, 4) if a1_value is not None else None,  # 법안처리율 자체가 risk
        "A2": norm("A2", raw["A2"]),
        "E1": norm("E1", raw["E1"]),
        "E2": norm("E2", raw["E2"]),
        "S2": norm("S2", raw["S2"]),
        "G1": norm("G1", raw["G1"]),
        "G2": norm("G2", raw["G2"]),
        "C1": norm("C1", raw["C1"]),
        "C2": norm("C2", raw["C2"]),
    }
    # S1 = 출산율 역 + 고령 평균
    s1_parts = [r for r in (norm("S1", raw["S1_tfr"]),
                            norm("S1_aged", raw["S1_aged"])) if r is not None]
    risk["S1"] = round(sum(s1_parts) / len(s1_parts), 4) if s1_parts else None

    score = wsm = 0.0
    for var, w in NATIONAL_WEIGHTS.items():
        if risk.get(var) is not None:
            score += risk[var] * w
            wsm += w
    eta = round(1 - score / wsm, 3) if wsm > 0 else None

    return {
        "eta": eta,
        "data_quality": f"{int(round(wsm * 100))}%",
        "raw_values": raw,
        "risk": risk,
        "weights": NATIONAL_WEIGHTS,
    }


def main():
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print("=" * 56)
    print(f"Λ¹² 12변수 KOSIS 수집 (전국 단위): {now}")
    print("=" * 56)

    print(f"\n[1] KOSIS ({len(NATIONAL_TABLES)}개 변수)")
    kosis = collect_kosis(NATIONAL_TABLES)

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

    print("\n[4] Λ¹² η 계산 (전국 12변수 가중합)")
    eta = calc_national_eta(kosis, a1["value"])
    print(f"  raw: " + "  ".join(f"{k}={v}" for k, v in eta["raw_values"].items() if v is not None))
    print(f"  risk: " + "  ".join(f"{k}={v}" for k, v in eta["risk"].items() if v is not None))
    print(f"  ▶ 전국 η = {eta['eta']}  (품질 {eta['data_quality']}, η↑=양호)")

    result = {
        "_updated": now,
        "_region": "national",
        "_verified": "전국 objL1 코드 전수 메타 검증 2026-05-24",
        "summary": summary,
        "eta": eta,
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
