#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재설계 변수 통합 수집 + Λ¹² 편입 설계 (⑤ data.go.kr 소방청 제외).

── Λ¹² 편입 설계 (확정) ──────────────────────────────────────────
η 투입 (구군 실수치, eta_inputs):
  ① 순이동률    = 순이동 건수 / 인구 × 100 (%)        ← DT_1B26A01 / eta.pop
  ② 재정자립도  = 그대로 (%)                          ← DT_1YL20921
  ④ 빈집률      = 빈집 호수 / 총주택 × 100 (%)         ← DT_1JU1512 / DT_1JU1501
η 제외 → 별도 패널 (separate_panel):
  ③ 1인당 GRDP  → 구군 공식 데이터 없음 (시도 단위만)  ← DT_1C86 (시도 26)
  ⑥ 가계부채    → 구군 공식 데이터 없음 (전국 단위만)  ← ECOS 151Y001
제약:
  · 가중치 소수 분해 금지   (η 가중치를 소수로 쪼개지 않음)
  · 인구비율 분해 금지      (시도/전국값을 인구비율로 구군 분해하지 않음)
표시 언어:
  · "측정 불가" 금지
  · "정부 공식 데이터 없음 (시도/전국 단위만 존재)" 사용
────────────────────────────────────────────────────────────────

키: KOSIS는 KOSIS_API_KEY(미설정시 내장 fallback). ECOS는 ECOS_API_KEY(GitHub Secrets, 미설정시 ⑥ 생략).
출력: data/redesign.json + ulsan.json['redesign'] 병합 (fetch_ulsan.py 이후 실행 전제).
"""
import os, json, datetime
from pathlib import Path
import requests

KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
ECOS_KEY  = os.environ.get("ECOS_API_KEY", "")
KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
OUTPUT = Path("data/redesign.json")
ULSAN_JSON = Path("data/ulsan.json")   # 병합 대상 + 구군 인구(eta.pop) 출처
TIMEOUT = 25

NO_DISTRICT = "정부 공식 데이터 없음 (시도/전국 단위만 존재)"  # ③⑥ 별도 패널 표시 언어

# 캐노니컬 키(31계열) → 이름 + 표별 지역코드 (울주군은 표마다 상이!)
GU = {
    "31110": {"name": "중구",   "c31": "31110", "c26": "26010", "c26c": "26010"},
    "31140": {"name": "남구",   "c31": "31140", "c26": "26020", "c26c": "26020"},
    "31170": {"name": "동구",   "c31": "31170", "c26": "26030", "c26c": "26030"},
    "31200": {"name": "북구",   "c31": "31200", "c26": "26040", "c26c": "26040"},
    "31710": {"name": "울주군", "c31": "31710", "c26": "26310", "c26c": "26510"},
}
REV31  = {v["c31"]: k for k, v in GU.items()}
REV26  = {v["c26"]: k for k, v in GU.items()}
REV26C = {v["c26c"]: k for k, v in GU.items()}


def kosis(tbl, itm, objL1, prdSe="Y", extra=None):
    p = {"method": "getList", "apiKey": KOSIS_KEY, "format": "json", "jsonVD": "Y",
         "orgId": "101", "tblId": tbl, "itmId": itm, "objL1": objL1,
         "prdSe": prdSe, "newEstPrdCnt": "1"}
    if extra:
        p.update(extra)
    d = requests.get(KOSIS_BASE, params=p, timeout=TIMEOUT).json()
    if isinstance(d, dict) and "err" in d:
        raise RuntimeError(f"{tbl} err={d.get('err')} {d.get('errMsg','')[:60]}")
    return d


def f2(v):
    try: return float(v)
    except: return None


def load_pop():
    """구군 인구 — fetch_ulsan.py가 먼저 채운 ulsan.json eta.pop 에서 읽음."""
    pop = {k: None for k in GU}
    if ULSAN_JSON.exists():
        try:
            u = json.load(open(ULSAN_JSON, encoding="utf-8"))
            for k in GU:
                pop[k] = u.get("eta", {}).get(k, {}).get("pop")
        except Exception:
            pass
    return pop


# ── ① 순이동률 = 건수/인구 × 100 ──
def collect_migration(out, pop):
    codes = " ".join(g["c31"] for g in GU.values())
    rows = kosis("DT_1B26A01", "T25", codes, prdSe="M", extra={"objL2": "0", "objL3": "000"})
    for r in rows:
        k = REV31.get(r.get("C1"))
        if not k:
            continue
        cnt = f2(r.get("DT"))
        out["raw"][k]["net_migration_1p"] = cnt
        p = pop.get(k)
        if cnt is not None and p:
            out["eta_inputs"][k]["net_migration_rate"] = round(cnt / p * 100, 3)
        out["meta"]["net_migration_period"] = r.get("PRD_DE")
        out["meta"]["net_migration_note"] = "1인 이동건수 기반 (건수/인구×100)"


# ── ② 재정자립도 = 그대로 (%) ──
def collect_fiscal(out):
    codes = " ".join(g["c26"] for g in GU.values())
    rows = kosis("DT_1YL20921", "ALL", codes, prdSe="Y")
    picked = {}
    for r in rows:
        k = REV26.get(r.get("C1"))
        if not k:
            continue
        if k not in picked or "개편전" in (r.get("ITM_NM") or ""):
            picked[k] = (f2(r.get("DT")), r.get("PRD_DE"))
    for k, (val, prd) in picked.items():
        out["eta_inputs"][k]["fiscal_independence"] = val
        out["meta"]["fiscal_period"] = prd


# ── ③ 1인당 GRDP → 별도 패널 (시도 단위, 구군 부재) ──
def collect_grdp(out):
    rows = kosis("DT_1C86", "T1", "26", prdSe="Y")
    r = rows[0]
    out["separate_panel"]["grdp_per_capita"] = {
        "scope": "시도(울산광역시)", "value": f2(r.get("DT")), "unit": r.get("UNIT_NM"),
        "period": r.get("PRD_DE"), "district_status": NO_DISTRICT,
    }
    out["meta"]["grdp_period"] = r.get("PRD_DE")


# ── ④ 빈집률 = 빈집호수/총주택 × 100 ──
def collect_vacant(out):
    codes = " ".join(g["c26c"] for g in GU.values())
    vac = kosis("DT_1JU1512", "T000", codes, prdSe="Y", extra={"objL2": "00"})
    tot = kosis("DT_1JU1501", "T10", codes, prdSe="Y")
    totmap = {REV26C.get(r.get("C1")): f2(r.get("DT")) for r in tot if REV26C.get(r.get("C1"))}
    for r in vac:
        k = REV26C.get(r.get("C1"))
        if not k:
            continue
        vh = f2(r.get("DT"))
        th = totmap.get(k)
        out["raw"][k]["vacant_houses"] = vh
        out["raw"][k]["total_houses"] = th
        if vh is not None and th:
            out["eta_inputs"][k]["vacancy_rate"] = round(vh / th * 100, 2)
        out["meta"]["vacant_period"] = r.get("PRD_DE")


# ── ⑥ 가계부채 → 별도 패널 (전국 단위, 구군 부재) ──
def collect_household_credit(out):
    if not ECOS_KEY:
        out["separate_panel"]["household_credit"] = {
            "scope": "전국", "value": None, "district_status": NO_DISTRICT,
            "_note": "ECOS_API_KEY 미설정 — ⑥ 생략",
        }
        return
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}"
           f"/json/kr/1/20/151Y001/A/2015/2030/1000000")
    d = requests.get(url, timeout=TIMEOUT).json()
    rows = d.get("StatisticSearch", {}).get("row") or [{}]
    row = max(rows, key=lambda r: r.get("TIME", ""))
    out["separate_panel"]["household_credit"] = {
        "scope": "전국", "value": f2(row.get("DATA_VALUE")), "unit": row.get("UNIT_NAME"),
        "period": row.get("TIME"), "district_status": NO_DISTRICT,
    }
    out["meta"]["household_credit_period"] = row.get("TIME")


def main():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    pop = load_pop()
    out = {
        "_updated": now,
        "_design": {
            "eta_inputs": {"①순이동률": "건수/인구×100(%)", "②재정자립도": "그대로(%)",
                           "④빈집률": "호수/총주택×100(%)"},
            "separate_panel": {"③1인당GRDP": "시도단위(구군 부재)", "⑥가계부채": "전국단위(구군 부재)"},
            "constraints": ["가중치 소수 분해 금지", "인구비율 분해 금지(시도/전국값 구군 미분해)"],
            "labeling": NO_DISTRICT + " — '측정 불가' 금지",
        },
        "meta": {},
        "eta_inputs": {k: {"name": v["name"]} for k, v in GU.items()},
        "raw": {k: {"pop": pop.get(k)} for k in GU},
        "separate_panel": {},
    }
    steps = [
        ("① 순이동률",   lambda: collect_migration(out, pop)),
        ("② 재정자립도", lambda: collect_fiscal(out)),
        ("③ GRDP(패널)", lambda: collect_grdp(out)),
        ("④ 빈집률",     lambda: collect_vacant(out)),
        ("⑥ 가계부채(패널)", lambda: collect_household_credit(out)),
    ]
    print("=" * 52)
    print(f"재설계 변수 수집 + Λ¹² 편입: {now}")
    print("=" * 52)
    ok = 0
    for label, fn in steps:
        try:
            fn()
            print(f"  [{label}] OK"); ok += 1
        except Exception as e:
            print(f"  [{label}] FAIL: {e}")
            out.setdefault("_errors", {})[label] = str(e)[:160]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUTPUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    if ULSAN_JSON.exists():
        try:
            u = json.load(open(ULSAN_JSON, encoding="utf-8"))
            u["redesign"] = out
            json.dump(u, open(ULSAN_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"병합: {ULSAN_JSON}['redesign'] 갱신")
        except Exception as e:
            print(f"병합 실패({ULSAN_JSON}): {e}")
    else:
        print(f"병합 생략: {ULSAN_JSON} 없음 (fetch_ulsan.py 먼저 실행 필요)")

    print(f"\n저장: {OUTPUT} ({ok}/5)")
    print("[η 투입 — 구군 실수치]")
    for k, v in out["eta_inputs"].items():
        print(f"  {v['name']:4s}: 순이동률={v.get('net_migration_rate')}% "
              f"재정={v.get('fiscal_independence')}% 빈집률={v.get('vacancy_rate')}%")
    sp = out["separate_panel"]
    print("[별도 패널 — 구군 공식데이터 없음]")
    print(f"  ③ 1인당GRDP(시도): {sp.get('grdp_per_capita',{}).get('value')}천원")
    print(f"  ⑥ 가계부채(전국): {sp.get('household_credit',{}).get('value')}십억원")


if __name__ == "__main__":
    main()
