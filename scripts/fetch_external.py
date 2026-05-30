#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""에어코리아·아파트·BIS 실측 파이프라인
data.go.kr 3종 API 수집 후 data/ulsan.json 에 병합.

환경변수:
  DATA_GO_KR — data.go.kr 서비스키 (GitHub Secrets)
"""
import os, json, time, datetime
from pathlib import Path
import requests

DATA_GO_KR = os.environ.get("DATA_GO_KR", "")
ULSAN_JSON = Path("data/ulsan.json")
TIMEOUT = 20
KST = datetime.timezone(datetime.timedelta(hours=9))

GU_KEYS  = ["junggu", "namgu", "donggu", "bukgu", "ulju"]
GU_NAMES = {"junggu":"중구","namgu":"남구","donggu":"동구","bukgu":"북구","ulju":"울주군"}

# ① 에어코리아 측정소 (구군별 대표)
AIR_STATIONS = {
    "junggu":"교동","namgu":"달동","donggu":"화정동","bukgu":"농소동","ulju":"언양",
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
AIR_URL = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"

def collect_air(key):
    result = {}
    for gu, station in AIR_STATIONS.items():
        params = {"serviceKey":key,"stationName":station,"dataTerm":"DAILY",
                  "pageNo":"1","numOfRows":"1","returnType":"json","ver":"1.3"}
        try:
            r = requests.get(AIR_URL, params=params, timeout=TIMEOUT)
            items = r.json().get("response",{}).get("body",{}).get("items") or []
            if not items:
                print(f"  에어코리아 [{gu}/{station}] 데이터 없음")
                result[gu] = {"pm25":None,"pm10":None,"cai":None,"station":station}
                continue
            row = items[0]
            pm25 = _float(row.get("pm25Value"))
            pm10 = _float(row.get("pm10Value"))
            cai  = _int(row.get("khaiValue"))
            result[gu] = {"pm25":pm25,"pm10":pm10,"cai":cai,
                          "station":station,"measured_at":row.get("dataTime")}
            print(f"  에어코리아 [{gu}/{station}] PM2.5={pm25} PM10={pm10} CAI={cai}")
        except Exception as e:
            print(f"  에어코리아 [{gu}] ERR: {e}")
            result[gu] = {"pm25":None,"pm10":None,"cai":None,
                          "station":station,"error":str(e)[:80]}
        time.sleep(0.3)
    return result

# ══════════════════════════════════════════════════════
# ② 아파트 실거래가 (최근 3개월 평균 만원/㎡)
# ══════════════════════════════════════════════════════
APT_URL = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"

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
        trades = []
        for ym in months:
            params = {"serviceKey":key,"LAWD_CD":lawd,"DEAL_YMD":ym,
                      "pageNo":"1","numOfRows":"100"}
            try:
                r = requests.get(APT_URL, params=params, timeout=TIMEOUT)
                items = r.json().get("response",{}).get("body",{}).get("items",{}).get("item") or []
                if isinstance(items, dict): items = [items]
                for row in items:
                    price = _float(str(row.get("거래금액","")).replace(",",""))
                    area  = _float(row.get("전용면적"))
                    if price and area and area > 0:
                        trades.append((price, area))
            except Exception as e:
                print(f"  아파트 [{gu}/{ym}] ERR: {e}")
            time.sleep(0.2)
        if trades:
            avg = round(sum(p/a for p,a in trades) / len(trades), 1)
            result[gu] = {"avg_price_per_sqm":avg,"trade_count":len(trades),"period_months":months}
            print(f"  아파트 [{gu}] 평균 {avg:,.1f}만원/㎡ ({len(trades)}건)")
        else:
            result[gu] = {"avg_price_per_sqm":None,"trade_count":0,"period_months":months}
            print(f"  아파트 [{gu}] 거래 없음 ({months})")
    return result

# ══════════════════════════════════════════════════════
# ③ 울산 BIS 버스정보 (data.go.kr 15052669)
# ══════════════════════════════════════════════════════
BIS_ROUTE_URL = "http://apis.data.go.kr/6310000/busRouteService/getBusRouteList"
BIS_STATS_URL = "http://apis.data.go.kr/6310000/busStatsService/getBusStatsList"

def collect_bus(key):
    result = {"total_routes":None,"daily_riders":None}
    try:
        params = {"serviceKey":key,"pageNo":"1","numOfRows":"1","returnType":"json"}
        d = requests.get(BIS_ROUTE_URL, params=params, timeout=TIMEOUT).json()
        total = d.get("response",{}).get("body",{}).get("totalCount")
        if total is not None:
            result["total_routes"] = int(total)
            print(f"  BIS 노선수: {total}개")
        else:
            print(f"  BIS 노선수 파싱 실패: {str(d)[:80]}")
    except Exception as e:
        print(f"  BIS 노선수 ERR: {e}"); result["error_routes"] = str(e)[:80]
    time.sleep(0.3)
    try:
        params = {"serviceKey":key,"pageNo":"1","numOfRows":"1","returnType":"json"}
        d = requests.get(BIS_STATS_URL, params=params, timeout=TIMEOUT).json()
        items = d.get("response",{}).get("body",{}).get("items",{}).get("item") or []
        if isinstance(items, dict): items = [items]
        if items:
            riders = _int(items[0].get("dailyRiders") or items[0].get("dayAvgPsgrCnt"))
            result["daily_riders"] = riders
            print(f"  BIS 일평균 이용객: {riders}")
        else:
            print("  BIS 이용객 데이터 없음")
    except Exception as e:
        print(f"  BIS 이용객 ERR: {e}"); result["error_riders"] = str(e)[:80]
    return result

# ══════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════
def main():
    import sys
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print("=" * 52)
    print(f"외부 데이터 파이프라인 (data.go.kr 3종): {now}")
    print("=" * 52)
    if not DATA_GO_KR:
        print("⚠️  DATA_GO_KR 환경변수 없음 — GitHub Secrets 확인 필요")
        key = ""
    else:
        key = DATA_GO_KR
        print(f"  서비스키: {key[:8]}...")

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

    if ULSAN_JSON.exists():
        try:
            u = json.loads(ULSAN_JSON.read_text(encoding="utf-8"))
            u["air_quality"] = ext["air_quality"]
            u["apt_price"]   = ext["apt_price"]
            u["bus_info"]    = ext["bus_info"]
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

if __name__ == "__main__":
    main()
