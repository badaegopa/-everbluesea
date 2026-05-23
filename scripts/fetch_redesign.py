#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재설계 변수 5종 통합 수집 (⑤ data.go.kr 소방청 제외).

수집 변수:
  ① 순이동(1인이동건수)  KOSIS DT_1B26A01  itm=T25, objL1=행정구역(31계열), objL2=성0, objL3=연령000, M
  ② 재정자립도           KOSIS DT_1YL20921 26계열(울주군=26310), Y  ※제시 DT_1YL20711은 오류
  ③ 1인당 GRDP          KOSIS DT_1C86     itm=T1, 시도 26(울산), Y  ※시도단위(구군 분해 불가)
  ④ 빈집(호)             KOSIS DT_1JU1512  itm=T000, objL2=00, census26계열(★울주군=26510), Y
  ⑥ 가계부채             ECOS  151Y001     item=1000000 가계신용, A  ※전국단위

키: KOSIS는 환경변수 KOSIS_API_KEY(미설정시 내장 fallback). ECOS는 ECOS_API_KEY(GitHub Secrets, 미설정시 ⑥ 생략).
출력: data/redesign.json
"""
import os, json, datetime
from pathlib import Path
import requests

KOSIS_KEY = os.environ.get("KOSIS_API_KEY", "MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=")
ECOS_KEY  = os.environ.get("ECOS_API_KEY", "")
KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
OUTPUT = Path("data/redesign.json")
ULSAN_JSON = Path("data/ulsan.json")   # 병합 대상 (fetch_ulsan.py 이후 실행)
TIMEOUT = 25

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
    r = requests.get(KOSIS_BASE, params=p, timeout=TIMEOUT)
    d = r.json()
    if isinstance(d, dict) and "err" in d:
        raise RuntimeError(f"{tbl} err={d.get('err')} {d.get('errMsg','')[:60]}")
    return d


def f2(v):
    try: return float(v)
    except: return None


def collect_migration(out):
    """① 순이동 — 31계열."""
    codes = " ".join(g["c31"] for g in GU.values())
    rows = kosis("DT_1B26A01", "T25", codes, prdSe="M", extra={"objL2": "0", "objL3": "000"})
    for r in rows:
        k = REV31.get(r.get("C1"))
        if k:
            out["districts"][k]["net_migration_1p"] = f2(r.get("DT"))
            out["meta"]["net_migration_period"] = r.get("PRD_DE")


def collect_fiscal(out):
    """② 재정자립도 — 26계열, 세입과목개편전 우선."""
    codes = " ".join(g["c26"] for g in GU.values())
    rows = kosis("DT_1YL20921", "ALL", codes, prdSe="Y")
    picked = {}
    for r in rows:
        k = REV26.get(r.get("C1"))
        if not k:
            continue
        # 개편전 우선, 없으면 첫 값
        if k not in picked or "개편전" in (r.get("ITM_NM") or ""):
            picked[k] = (f2(r.get("DT")), r.get("PRD_DE"))
    for k, (val, prd) in picked.items():
        out["districts"][k]["fiscal_independence"] = val
        out["meta"]["fiscal_period"] = prd


def collect_grdp(out):
    """③ 1인당 GRDP — 시도 26(울산), 구군 분해 불가 → sido 레벨 저장."""
    rows = kosis("DT_1C86", "T1", "26", prdSe="Y")
    for r in rows:
        out["sido_ulsan"]["grdp_per_capita"] = f2(r.get("DT"))
        out["sido_ulsan"]["grdp_unit"] = r.get("UNIT_NM")
        out["meta"]["grdp_period"] = r.get("PRD_DE")
        break


def collect_vacant(out):
    """④ 빈집(호) — census 26계열(울주군=26510)."""
    codes = " ".join(g["c26c"] for g in GU.values())
    rows = kosis("DT_1JU1512", "T000", codes, prdSe="Y", extra={"objL2": "00"})
    for r in rows:
        k = REV26C.get(r.get("C1"))
        if k:
            out["districts"][k]["vacant_houses"] = f2(r.get("DT"))
            out["meta"]["vacant_period"] = r.get("PRD_DE")


def collect_household_credit(out):
    """⑥ 가계부채 — ECOS 151Y001 item 1000000(가계신용), 전국."""
    if not ECOS_KEY:
        out["national"]["household_credit"] = None
        out["national"]["_note"] = "ECOS_API_KEY 미설정 — ⑥ 생략"
        return
    # ECOS는 시간 오름차순 반환 → 넉넉히 받아 최신(TIME 최대) 선택
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}"
           f"/json/kr/1/20/151Y001/A/2015/2030/1000000")
    d = requests.get(url, timeout=TIMEOUT).json()
    rows = d.get("StatisticSearch", {}).get("row") or [{}]
    row = max(rows, key=lambda r: r.get("TIME", ""))
    out["national"]["household_credit"] = f2(row.get("DATA_VALUE"))
    out["national"]["household_credit_unit"] = row.get("UNIT_NAME")
    out["meta"]["household_credit_period"] = row.get("TIME")


def main():
    KST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    out = {
        "_updated": now,
        "_source": "재설계 5종 (①순이동 ②재정자립도 ③GRDP ④빈집 ⑥가계부채). ⑤소방청 제외.",
        "meta": {},
        "districts": {k: {"name": v["name"]} for k, v in GU.items()},
        "sido_ulsan": {},
        "national": {},
    }
    steps = [
        ("① 순이동",     collect_migration),
        ("② 재정자립도", collect_fiscal),
        ("③ 1인당 GRDP", collect_grdp),
        ("④ 빈집",       collect_vacant),
        ("⑥ 가계부채",   collect_household_credit),
    ]
    print("=" * 52)
    print(f"재설계 변수 5종 통합 수집: {now}")
    print("=" * 52)
    ok = 0
    for label, fn in steps:
        try:
            fn(out)
            print(f"  [{label}] OK")
            ok += 1
        except Exception as e:
            print(f"  [{label}] FAIL: {e}")
            out.setdefault("_errors", {})[label] = str(e)[:160]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # ── ulsan.json 에 top-level 'redesign' 키로 병합 (fetch_ulsan.py 이후 실행 전제) ──
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

    print(f"\n저장: {OUTPUT} ({ok}/5 수집)")
    for k, v in out["districts"].items():
        print(f"  {v['name']:4s}: 순이동={v.get('net_migration_1p')} "
              f"재정={v.get('fiscal_independence')}% 빈집={v.get('vacant_houses')}호")
    print(f"  [울산 시도] 1인당GRDP={out['sido_ulsan'].get('grdp_per_capita')}{out['sido_ulsan'].get('grdp_unit','')}")
    print(f"  [전국] 가계신용={out['national'].get('household_credit')}{out['national'].get('household_credit_unit','')}")


if __name__ == "__main__":
    main()
