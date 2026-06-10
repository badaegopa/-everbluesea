#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""에어코리아·아파트·BIS 실측 파이프라인
data.go.kr 3종 API 수집 후 data/ulsan.json 에 병합.

환경변수:
  DATA_GO_KR — data.go.kr 서비스키 (GitHub Secrets)
  KOSIS      — KOSIS OpenAPI 키 (Base64 그대로 사용, 디코딩 금지)
"""
import os, json, time, datetime
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

DATA_GO_KR = os.environ.get("DATA_GO_KR", "")
KOSIS      = os.environ.get("KOSIS", "")
ULSAN_JSON = Path("data/ulsan.json")
TIMEOUT = 20
KST = datetime.timezone(datetime.timedelta(hours=9))

GU_KEYS  = ["junggu", "namgu", "donggu", "bukgu", "ulju"]
GU_NAMES = {"junggu":"중구","namgu":"남구","donggu":"동구","bukgu":"북구","ulju":"울주군"}

# ① 에어코리아 측정소 (구군별 대표)
AIR_STATIONS = {
    "junggu":"성남동","namgu":"삼산동","donggu":"전하동","bukgu":"농소동","ulju":"삼남읍",
}

# ② 아파트 법정동 코드 (LAWD_CD 앞 5자리, 31계열)
APT_LAWD = {
    "junggu":"31110","namgu":"31140","donggu":"31170","bukgu":"31200","ulju":"31710",
}

def _float(v):
    try: return float(str(v).replace(",","").strip()) if v not in (None,"","-") else None
    except: return None

def _int(v):
    try: return int(str(v).replace(",","").strip()) if v not in (None,"","-") else None
    except: return None

# ══════════════════════════════════════════════════════
# ① 에어코리아 대기질
# ══════════════════════════════════════════════════════
AIR_URL = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
def collect_air(key):
    """울산 시도 전체를 1회 호출 → 구별 대표 측정소 값만 추출."""
    result = {gu: {"pm25":None,"pm10":None,"cai":None,"station":st}
              for gu, st in AIR_STATIONS.items()}
    params = {"serviceKey":key,"sidoName":"울산","returnType":"json",
              "numOfRows":"100","pageNo":"1","ver":"1.3"}
    try:
        r = requests.get(AIR_URL, params=params, timeout=TIMEOUT)
        items = r.json().get("response",{}).get("body",{}).get("items") or []
        by_name = {it.get("stationName"): it for it in items}
        for gu, st in AIR_STATIONS.items():
            row = by_name.get(st)
            if not row:
                print(f"  에어코리아 [{gu}/{st}] 측정소 응답없음(점검중?)")
                continue
            pm25 = _float(row.get("pm25Value")); pm10 = _float(row.get("pm10Value"))
            cai  = _int(row.get("khaiValue"))
            result[gu] = {"pm25":pm25,"pm10":pm10,"cai":cai,
                          "station":st,"measured_at":row.get("dataTime")}
            print(f"  에어코리아 [{gu}/{st}] PM2.5={pm25} PM10={pm10} CAI={cai}")
    except Exception as e:
        print(f"  에어코리아 시도조회 ERR: {e}")
        for gu in result: result[gu]["error"]=str(e)[:80]
    return result

# ══════════════════════════════════════════════════════
# ② 아파트 실거래가 (최근 3개월 평균 만원/㎡)
# ══════════════════════════════════════════════════════
APT_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"

def _recent_months(n=3):
    today = datetime.datetime.now(KST)
    months = []
    for i in range(n):
        m, y = today.month - i, today.year
        while m <= 0: m += 12; y -= 1
        months.append(f"{y}{m:02d}")
    return months

def collect_apt(key):
    result = {}
    months = _recent_months(3)
    for gu, lawd in APT_LAWD.items():
        trades = []          # (price, area) 표본 — 평균 ㎡단가 계산용
        total_deals = 0      # totalCount 합 — 실제 거래량
        for ym in months:
            params = {"serviceKey":key,"LAWD_CD":lawd,"DEAL_YMD":ym,
                      "pageNo":"1","numOfRows":"1000"}
            try:
                r = requests.get(APT_URL, params=params, timeout=TIMEOUT)
                root = ET.fromstring(r.content)
                rc = root.findtext(".//resultCode")
                if rc not in (None, "000", "00"):
                    print(f"  아파트 [{gu}/{ym}] API코드 {rc}: {root.findtext('.//resultMsg')}")
                    time.sleep(0.2); continue
                tc = _int(root.findtext(".//totalCount"))
                if tc: total_deals += tc
                for it in root.findall(".//item"):
                    price = _float((it.findtext("dealAmount") or "").replace(",",""))
                    area  = _float(it.findtext("excluUseAr"))
                    if price and area and area > 0:
                        trades.append((price, area))
            except Exception as e:
                print(f"  아파트 [{gu}/{ym}] ERR: {e}")
            time.sleep(0.2)
        if trades:
            avg = round(sum(p/a for p,a in trades) / len(trades), 1)
            result[gu] = {"avg_price_per_sqm":avg,"trade_count":total_deals,
                          "sampled":len(trades),"period_months":months}
            print(f"  아파트 [{gu}] 평균 {avg:,.1f}만원/㎡ (실거래 {total_deals}건/표본 {len(trades)})")
        else:
            result[gu] = {"avg_price_per_sqm":None,"trade_count":0,
                          "sampled":0,"period_months":months}
            print(f"  아파트 [{gu}] 거래 없음 ({months})")
    return result

# ══════════════════════════════════════════════════════
# ③ 울산 BIS 버스정보 (data.go.kr 15052669)
# ══════════════════════════════════════════════════════
# ★TAGO 도시코드: 울산=26 (인구표 31계열·SGIS adm_cd 31과 또 다름 — API별 코드 상이)
BIS_ROUTE_URL   = "http://apis.data.go.kr/1613000/BusRouteInfoInqireService/getRouteNoList"
BIS_STN_URL     = "http://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
ULSAN_CITY_CODE = "26"
def collect_bus(key):
    result = {"total_routes":None,"total_stations":None,"city_code":ULSAN_CITY_CODE}
    def _total(url):
        params = {"serviceKey":key,"cityCode":ULSAN_CITY_CODE,"numOfRows":"1","pageNo":"1"}
        r = requests.get(url, params=params, timeout=TIMEOUT)
        root = ET.fromstring(r.content)
        rc = root.findtext(".//resultCode")
        if rc not in ("00","000",None):
            raise RuntimeError(f"{rc} {root.findtext('.//resultMsg')}")
        return _int(root.findtext(".//totalCount"))
    try:
        result["total_routes"]   = _total(BIS_ROUTE_URL)
        time.sleep(0.3)
        result["total_stations"] = _total(BIS_STN_URL)
        result["measured_at"]    = datetime.datetime.now(KST).strftime("%Y-%m-%d")
        print(f"  버스 노선 {result['total_routes']} / 정류소 {result['total_stations']} (울산 전체, cityCode=26)")
    except Exception as e:
        print(f"  버스 ERR: {e}"); result["error"] = str(e)[:80]
    return result

# ══════════════════════════════════════════════════════
# ④ KRX 금시세 (금 99.99_1kg, srtnCd=04020000)
# ══════════════════════════════════════════════════════
GOLD_URL    = "https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"
GOLD_SRTNCD = "04020000"   # 금 99.99_1kg

def collect_gold(key):
    """최근 10일 구간 조회 → srtnCd=04020000 최신 거래일(basDt) 1건 추출."""
    result = {"clpr":None,"vs":None,"fltRt":None,"mkp":None,
              "hipr":None,"lopr":None,"trqu":None,"basDt":None}
    today = datetime.datetime.now(KST)
    begin = (today - datetime.timedelta(days=10)).strftime("%Y%m%d")
    end   = today.strftime("%Y%m%d")
    params = {"serviceKey":key,"resultType":"json",
              "beginBasDt":begin,"endBasDt":end,"numOfRows":"10"}
    try:
        r = requests.get(GOLD_URL, params=params, timeout=TIMEOUT)
        items = r.json().get("response",{}).get("body",{}).get("items",{}).get("item") or []
        if isinstance(items, dict): items = [items]
        rows = [it for it in items if it.get("srtnCd") == GOLD_SRTNCD]
        if not rows:
            print(f"  금시세 [{GOLD_SRTNCD}] 응답없음 ({begin}~{end})")
            return result
        latest = max(rows, key=lambda it: it.get("basDt",""))
        result = {
            "clpr": _float(latest.get("clpr")),   # 종가
            "vs":   _float(latest.get("vs")),     # 대비
            "fltRt":_float(latest.get("fltRt")),  # 등락률
            "mkp":  _float(latest.get("mkp")),    # 시가
            "hipr": _float(latest.get("hipr")),   # 고가
            "lopr": _float(latest.get("lopr")),   # 저가
            "trqu": _int(latest.get("trqu")),     # 거래량
            "basDt":latest.get("basDt"),          # 기준일자
        }
        print(f"  금시세 [{result['basDt']}] 종가 {result['clpr']:,}원 "
              f"({result['fltRt']:+}%) 거래량 {result['trqu']}")
    except Exception as e:
        print(f"  금시세 ERR: {e}"); result["error"] = str(e)[:80]
    return result

# ══════════════════════════════════════════════════════
# ⑤ KOSIS 장래인구추계 (DT_1BPA401, 중위추계 총인구)
# ══════════════════════════════════════════════════════
KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

def collect_population(key):
    """장래인구추계 중위추계(C1=13)·총인구(C2=10) 연도별 시계열 추출."""
    result = {"data": []}
    params = {"method":"getList","apiKey":key,
              "orgId":"101","tblId":"DT_1BPA401",
              "objL1":"ALL","objL2":"ALL","itmId":"T10+",
              "prdSe":"Y","format":"json","jsonVD":"Y"}
    try:
        r = requests.get(KOSIS_URL, params=params, timeout=TIMEOUT)
        rows = r.json()
        if isinstance(rows, dict):   # 에러 응답({"err":..,"errMsg":..})
            raise RuntimeError(rows.get("errMsg") or rows.get("err") or str(rows))
        data = []
        for it in rows:
            if it.get("C1") != "13" or it.get("C2") != "10":   # 중위추계+총인구만
                continue
            data.append({
                "year":       it.get("PRD_DE"),
                "population":  _int(it.get("DT")),
                "scenario":   it.get("C1_NM") or "중위추계",
            })
        data.sort(key=lambda d: d.get("year") or "")
        result["data"] = data
        if data:
            print(f"  인구추계 중위·총인구 {len(data)}개 연도 "
                  f"({data[0]['year']}~{data[-1]['year']})")
        else:
            print("  인구추계 필터(C1=13·C2=10) 결과 없음")
    except Exception as e:
        print(f"  인구추계 ERR: {e}"); result["error"] = str(e)[:80]
    return result

# ══════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════
def main():
    import sys
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print("=" * 52)
    print(f"외부 데이터 파이프라인 (data.go.kr 4종 + KOSIS): {now}")
    print("=" * 52)
    if not DATA_GO_KR:
        print("⚠️  DATA_GO_KR 환경변수 없음 — GitHub Secrets 확인 필요")
        key = ""
    else:
        key = DATA_GO_KR
        print(f"  서비스키: {key[:8]}...")
    if not KOSIS:
        print("⚠️  KOSIS 환경변수 없음 — 인구추계 건너뜀")
    else:
        print(f"  KOSIS키: {KOSIS[:8]}...")

    ext = {"_updated": now}

    print("\n[① 에어코리아 대기질]")
    ext["air_quality"] = collect_air(key) if key else {
        gu: {"pm25":None,"pm10":None,"cai":None,"station":s,"error":"DATA_GO_KR 미설정"}
        for gu, s in AIR_STATIONS.items()
    }

    print("\n[② 아파트 실거래가]")
    ext["apt_price"] = collect_apt(key) if key else {
        gu: {"avg_price_per_sqm":None,"trade_count":0,"error":"DATA_GO_KR 미설정"}
        for gu in APT_LAWD
    }

    print("\n[③ 울산 BIS 버스정보]")
    ext["bus_info"] = collect_bus(key) if key else {
        "total_routes":None,"daily_riders":None,"error":"DATA_GO_KR 미설정"
    }

    print("\n[④ KRX 금시세]")
    ext["gold_price"] = collect_gold(key) if key else {
        "clpr":None,"basDt":None,"error":"DATA_GO_KR 미설정"
    }

    print("\n[⑤ KOSIS 장래인구추계]")
    ext["population_forecast"] = collect_population(KOSIS) if KOSIS else {
        "data":[],"error":"KOSIS 미설정"
    }

    if ULSAN_JSON.exists():
        try:
            u = json.loads(ULSAN_JSON.read_text(encoding="utf-8"))
            u["air_quality"] = ext["air_quality"]
            u["apt_price"]   = ext["apt_price"]
            u["bus_info"]    = ext["bus_info"]
            u["gold_price"]  = ext["gold_price"]
            u["population_forecast"] = ext["population_forecast"]
            ULSAN_JSON.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n✅ 병합 완료 → {ULSAN_JSON}")
        except Exception as e:
            print(f"\n병합 실패({ULSAN_JSON}): {e}"); sys.exit(1)
    else:
        print(f"\n⚠️  {ULSAN_JSON} 없음 — fetch_ulsan.py 먼저 실행 필요")

    print("\n[요약]")
    for gu in GU_KEYS:
        aq = ext["air_quality"].get(gu, {})
        ap = ext["apt_price"].get(gu, {})
        print(f"  {GU_NAMES[gu]:4s}: PM2.5={aq.get('pm25')} PM10={aq.get('pm10')} "
              f"CAI={aq.get('cai')} | 아파트={ap.get('avg_price_per_sqm')}만원/㎡")
    bi = ext["bus_info"]
    print(f"  BIS: 노선수={bi.get('total_routes')} 일평균이용객={bi.get('daily_riders')}")
    gp = ext["gold_price"]
    print(f"  금시세: {gp.get('basDt')} 종가={gp.get('clpr')}원 등락률={gp.get('fltRt')}%")
    pf = ext["population_forecast"]
    pd = pf.get("data") or []
    if pd:
        print(f"  인구추계: {pd[0].get('year')}~{pd[-1].get('year')} "
              f"({len(pd)}개 연도) 최신 {pd[-1].get('population')}명")
    else:
        print(f"  인구추계: 데이터 없음 ({pf.get('error','')})")

if __name__ == "__main__":
    main()
