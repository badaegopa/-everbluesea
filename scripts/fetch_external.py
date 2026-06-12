#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""에어코리아·아파트·BIS 실측 파이프라인
data.go.kr 3종 API 수집 후 data/ulsan.json 에 병합.

환경변수:
  DATA_GO_KR — data.go.kr 서비스키 (GitHub Secrets)
  KOSIS      — KOSIS OpenAPI 키 (Base64 그대로 사용, 디코딩 금지)
  ECOS       — 한국은행 ECOS OpenAPI 키
"""
import os, json, re, time, datetime
import xml.etree.ElementTree as ET
from pathlib import Path
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATA_GO_KR   = os.environ.get("DATA_GO_KR", "")
KOSIS        = os.environ.get("KOSIS", "")
ECOS         = os.environ.get("ECOS", "")
NKIS_API_KEY = os.environ.get("NKIS_API_KEY", "")
KICOX_KEY    = os.environ.get("DATA_GO_KR", "")   # 산업단지공단도 DATA_GO_KR Encoding 키 사용
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
# ⑥ ECOS 거시경제지표 (한국은행)
# ══════════════════════════════════════════════════════
ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

ECOS_ITEMS = [
    ("base_rate",  "722Y001", "0101000"),     # 기준금리
    ("usd_krw",    "731Y001", "0000001"),     # 달러환율
    ("cny_krw",    "731Y001", "0000053"),     # 위안환율
    ("bond_3yr",   "817Y002", "010200000"),   # 국고채 3년
    ("bond_10yr",  "817Y002", "010210000"),   # 국고채 10년
]

def collect_ecos(key):
    """최근 10일 구간 조회 → 항목별 최신 1건(DATA_VALUE) 추출."""
    today = datetime.datetime.now(KST)
    begin = (today - datetime.timedelta(days=10)).strftime("%Y%m%d")
    end   = today.strftime("%Y%m%d")
    result = {field: None for field, _, _ in ECOS_ITEMS}
    result["measured_at"] = None

    for field, stat_code, item_code in ECOS_ITEMS:
        url = f"{ECOS_BASE}/{key}/json/kr/1/1/{stat_code}/D/{begin}/{end}/{item_code}"
        try:
            r = requests.get(url, timeout=TIMEOUT)
            rows = r.json().get("StatisticSearch", {}).get("row") or []
            if not rows:
                print(f"  ECOS [{field}/{stat_code}/{item_code}] 응답없음 ({begin}~{end})")
                continue
            latest = max(rows, key=lambda x: x.get("TIME", ""))
            val = _float(latest.get("DATA_VALUE"))
            result[field] = val
            result["measured_at"] = latest.get("TIME")
            print(f"  ECOS [{field}] {latest.get('TIME')} = {val}")
        except Exception as e:
            print(f"  ECOS [{field}] ERR: {e}")
            result[f"{field}_error"] = str(e)[:80]

    return result

# ══════════════════════════════════════════════════════
# ⑦ NKIS 정책연구 (nkis.re.kr)
# ══════════════════════════════════════════════════════
NKIS_URL      = "https://nkis.re.kr/nkisApi/search/TongList.do"
NKIS_KEYWORDS = ["저출산", "고령화", "인구감소", "지역소멸", "사회동역학"]

def _parse_nkis_response(text):
    """JavaScript console.log 형태 또는 순수 JSON 응답 파싱."""
    for pat in [
        r'console\.log\s*\(({.+})\s*\)\s*;?',
        r'console\.log\s*\((.+)\)\s*;?',
    ]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def _extract_nkis_items(data):
    """다양한 응답 구조에서 items 리스트 추출."""
    if not data:
        return []
    candidates = [
        data.get("response", {}).get("body", {}).get("items"),
        data.get("body", {}).get("items"),
        data.get("items"),
        data.get("list"),
        data.get("data"),
        data.get("result"),
    ]
    for c in candidates:
        if not c:
            continue
        if isinstance(c, list):
            return c
        if isinstance(c, dict):
            inner = c.get("item") or c.get("list") or []
            if inner:
                return inner if isinstance(inner, list) else [inner]
    return []

def collect_nkis(key):
    """NKIS 정책연구 키워드별 최신 3건 수집."""
    result = {}
    for keyword in NKIS_KEYWORDS:
        params = {"serviceKey": key, "keyword": keyword,
                  "numOfRows": "3", "pageNo": "1"}
        try:
            r = requests.get(NKIS_URL, params=params, timeout=TIMEOUT, verify=False)
            data  = _parse_nkis_response(r.text)
            items = _extract_nkis_items(data)
            top3  = []
            for it in items[:3]:
                top3.append({
                    "title":     (it.get("title") or it.get("rptNm") or
                                  it.get("resTtl") or it.get("titleNm") or "").strip(),
                    "publisher": (it.get("publisher") or it.get("publishOrgan") or
                                  it.get("orgNm") or it.get("insttNm") or "").strip(),
                    "year":      str(it.get("publishYear") or it.get("year") or
                                     it.get("pubYear") or it.get("pblYear") or "").strip(),
                    "url":       (it.get("url") or it.get("fileUrl") or
                                  it.get("linkUrl") or it.get("oriUrl") or "").strip(),
                })
            result[keyword] = top3
            print(f"  NKIS [{keyword}] {len(top3)}건")
        except Exception as e:
            print(f"  NKIS [{keyword}] ERR: {e}")
            result[keyword] = []
    return result


# ══════════════════════════════════════════════════════
# ⑧ KOSIS 행정구역별 인구수 (DT_1B040A3)
# ══════════════════════════════════════════════════════
# 출처: 행정안전부 주민등록인구현황 (월별)
# itmId: T20=총인구 T21=남자 T22=여자
# objL1: 시도 코드 (울산=26)
KOSIS_POP_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

KOSIS_REGION_CODES = {
    "00": "전국",  "11": "서울", "26": "부산", "27": "대구",
    "28": "인천",  "29": "광주", "30": "대전", "31": "울산",
    "36": "세종",  "41": "경기", "51": "강원", "43": "충북",
    "44": "충남",  "52": "전북", "46": "전남", "47": "경북",
    "48": "경남",  "50": "제주",
}

def collect_kosis_regional_pop(key):
    """행정구역(시도)별 주민등록 인구수 최근 3개월 — DT_1B040A3."""
    result = {"data": [], "ulsan_total": None, "ulsan_male": None,
              "ulsan_female": None, "latest_period": None}
    params = {
        "method":       "getList",
        "apiKey":       key,
        "orgId":        "101",
        "tblId":        "DT_1B040A3",
        "itmId":        "T20+T21+T22+",
        "objL1":        "00+11+26+27+28+29+30+31+36+41+51+43+44+52+46+47+48+50+",
        "objL2":        "",
        "prdSe":        "M",
        "newEstPrdCnt": "3",
        "format":       "json",
        "jsonVD":       "Y",
    }
    try:
        r = requests.get(KOSIS_POP_URL, params=params, timeout=TIMEOUT)
        rows = r.json()
        if isinstance(rows, dict):
            raise RuntimeError(rows.get("errMsg") or rows.get("err") or str(rows))

        # 최신 기간 확인
        periods = sorted({row.get("PRD_DE", "") for row in rows if row.get("PRD_DE")}, reverse=True)
        latest = periods[0] if periods else None
        result["latest_period"] = latest

        # 최신 기간 기준 시도별 총인구 집계
        data = []
        for c1_code, region_name in KOSIS_REGION_CODES.items():
            total = next(
                (_int(row["DT"]) for row in rows
                 if row.get("C1") == c1_code
                 and row.get("ITM_ID") == "T20"
                 and row.get("PRD_DE") == latest),
                None
            )
            male = next(
                (_int(row["DT"]) for row in rows
                 if row.get("C1") == c1_code
                 and row.get("ITM_ID") == "T21"
                 and row.get("PRD_DE") == latest),
                None
            )
            female = next(
                (_int(row["DT"]) for row in rows
                 if row.get("C1") == c1_code
                 and row.get("ITM_ID") == "T22"
                 and row.get("PRD_DE") == latest),
                None
            )
            data.append({
                "region_code": c1_code,
                "region_name": region_name,
                "total": total,
                "male": male,
                "female": female,
                "period": latest,
            })

        result["data"] = data

        # 울산(C1=31) 별도 추출
        ulsan = next((d for d in data if d["region_code"] == "31"), None)
        if ulsan:
            result["ulsan_total"]  = ulsan["total"]
            result["ulsan_male"]   = ulsan["male"]
            result["ulsan_female"] = ulsan["female"]

        nat = next((d for d in data if d["region_code"] == "00"), None)
        print(f"  KOSIS 지역인구 [{latest}] 전국={nat['total']:,}" if nat and nat['total'] else
              f"  KOSIS 지역인구 [{latest}] 집계완료")
        if ulsan and ulsan["total"]:
            print(f"  → 울산 {ulsan['total']:,}명 (남:{ulsan['male']:,} 여:{ulsan['female']:,})")

    except Exception as e:
        print(f"  KOSIS 지역인구 ERR: {e}")
        result["error"] = str(e)[:80]
    return result


# ══════════════════════════════════════════════════════
# ⑨ 한국산업단지공단 산업동향 (KICOX) — 업종별 5종
# ══════════════════════════════════════════════════════
# Base URL: https://apis.data.go.kr/B550624/indparkstats
# serviceKey: Encoding 키 그대로 사용
# 날짜: srtStdrYm / endStdrYm (YYYYMM) 필수
# 응답: XML (type 파라미터 불필요)
# 개발계정 일일 500회 제한

KICOX_BASE = "https://apis.data.go.kr/B550624/indparkstats"
KICOX_SERVICES = [
    ("op_rate_detail",  "kicoxDetailOpRateStatsService",      "가동률 세부내역"),
    ("op_by_industry",  "kicoxOpRateByIndustryStatsService",  "업종별 가동률"),
    ("prod_by_industry","kicoxPrdRecByIndustryStatsService",  "업종별 생산실적"),
    ("export_by_industry","kicoxExportRecByIndustryStatsService","업종별 수출실적"),
    ("company_by_industry","kicoxOpCmpnyByIndustryStatsService","업종별 가동업체"),
]

def _kicox_recent_ym(offset_months=1):
    """기준년월: 현재 달에서 offset_months 전 (공단 데이터 1~2달 지연)."""
    today = datetime.datetime.now(KST)
    m, y = today.month - offset_months, today.year
    while m <= 0:
        m += 12; y -= 1
    return f"{y}{m:02d}"

def collect_kicox(key):
    """산업단지공단 업종별 동향 5종 수집 (XML 응답)."""
    result = {}
    srt = _kicox_recent_ym(3)   # 3개월 전부터
    end = _kicox_recent_ym(1)   # 1개월 전까지 (최신 확정치)

    for field, service, label in KICOX_SERVICES:
        url = f"{KICOX_BASE}/{service}"
        params = {
            "serviceKey":  key,
            "srtStdrYm":   srt,
            "endStdrYm":   end,
            "numOfRows":   "100",
            "pageNo":      "1",
        }
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
            root = ET.fromstring(r.content)

            # 결과코드 확인
            rc = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
            if rc and rc not in ("00", "000", "0000"):
                msg = root.findtext(".//resultMsg") or root.findtext(".//returnReasonMsg") or ""
                raise RuntimeError(f"code={rc} {msg}")

            items = root.findall(".//item")
            parsed = []
            for it in items:
                row = {child.tag: (child.text or "").strip() for child in it}
                parsed.append(row)

            result[field] = {
                "label":   label,
                "period":  f"{srt}~{end}",
                "count":   len(parsed),
                "data":    parsed,
            }
            print(f"  KICOX [{label}] {srt}~{end}: {len(parsed)}건")

            # 울산 단지 요약 (가동률 세부내역일 경우)
            if field == "op_rate_detail":
                ulsan_rows = [
                    r for r in parsed
                    if "울산" in (r.get("irsttNm") or r.get("irsttTyNm") or "")
                ]
                if ulsan_rows:
                    for ur in ulsan_rows[:3]:
                        rate = ur.get("opRateTotal") or ur.get("opRateBig") or "-"
                        nm   = ur.get("irsttNm") or ur.get("irsttTyNm") or ""
                        print(f"    └ {nm}: 가동률 {rate}%")

        except Exception as e:
            print(f"  KICOX [{label}] ERR: {e}")
            result[field] = {"label": label, "error": str(e)[:80], "data": []}

        time.sleep(0.3)   # API 부하 방지

    return result


# ══════════════════════════════════════════════════════
# 두레비즈 DURE-Biz — CBAM 카테고리
# 국가온실가스통계 6종 수집 함수 (orgId=106)
# 출처: 기후에너지환경부 온실가스종합정보센터
# 단위: 백만t CO₂eq. (지역별은 Gg CO₂eq.)
# ══════════════════════════════════════════════════════

KOSIS_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

GHG_TABLES = {
    "ghg_by_sector":   ("DT_106N_99_2800020", "13103130539T.1100001+",        "분야별 배출량 추이",     "Y", "5", "백만t"),
    "ghg_indicators":  ("DT_106N_99_2800019", "13103130540T.1100001+13103130540T.1100002+13103130540T.1100003+13103130540T.1100004+", "배출량 주요 지표", "Y", "5", "백만t"),
    "ghg_by_gas":      ("DT_106N_99_2800021", "13103130538T.1100001+",        "종류별 배출량 추이",     "Y", "5", "백만t"),
    "ghg_gas_sector":  ("DT_106N_99_2800025", "13103130541T.1100001+",        "종류별×분야별 배출량",   "Y", "5", "백만t"),
    "ghg_regional_direct": ("DT_106N_99_2800026", "13103844246T.10001+",      "지역별 배출량(직접)",    "Y", "3", "Gg"),
    "ghg_regional_indirect": ("DT_106N_99_2800027", "13103844245T.10001+",    "지역별 배출량(간접)",    "Y", "3", "Gg"),
}

def _fetch_kosis_ghg(key, tbl_id, itm_id, prd_se, cnt, label, unit):
    """KOSIS 온실가스 통계 공통 수집 함수"""
    result = {"label": label, "unit": unit, "data": [], "latest_year": None}
    params = {
        "method": "getList", "apiKey": key,
        "orgId": "106", "tblId": tbl_id,
        "itmId": itm_id,
        "objL1": "ALL", "objL2": "ALL",
        "objL3": "", "objL4": "", "objL5": "",
        "prdSe": prd_se, "newEstPrdCnt": cnt,
        "format": "json", "jsonVD": "Y",
    }
    try:
        r = requests.get(KOSIS_URL, params=params, timeout=TIMEOUT)
        rows = r.json()
        if isinstance(rows, dict):
            raise RuntimeError(rows.get("errMsg") or rows.get("err") or str(rows))
        years = sorted({row.get("PRD_DE","") for row in rows if row.get("PRD_DE")}, reverse=True)
        result["latest_year"] = years[0] if years else None
        result["data"] = rows
        print(f"  GHG [{label}] {result['latest_year']}: {len(rows)}건")
    except Exception as e:
        print(f"  GHG [{label}] ERR: {e}")
        result["error"] = str(e)[:80]
    return result


def collect_ghg_all(key):
    """온실가스 6종 전체 수집 — CBAM 카테고리 데이터 레이어"""
    result = {}
    for field, (tbl_id, itm_id, label, prd_se, cnt, unit) in GHG_TABLES.items():
        result[field] = _fetch_kosis_ghg(key, tbl_id, itm_id, prd_se, cnt, label, unit)
        time.sleep(0.3)
    return result


# ── 교차 연산 엔진 ──────────────────────────────────────
# 없던 데이터 창조: 시도 × 분야 × 가스 배출 매트릭스

def compute_cbam_exposure(ghg_all, ets_price_eur, eur_krw):
    """
    CBAM 노출액 교차 계산
    입력: 온실가스 6종 수집 결과 + EU ETS 가격 + 환율
    출력: 시도별 CBAM 노출액(억원) + 인증서 필요수량(tCO₂)

    계산 방식:
      ① 지역별 직접배출[시도][분야] (Gg CO₂eq.)
      ② 종류별×분야별[CO₂][분야] 비율 (전국 기준)
      ③ 시도 CO₂ 추정 = ①×②
      ④ CBAM 노출액 = ③(tCO₂) × ETS가격(€) × EUR/KRW
    """
    result = {"regions": {}, "national_total_gg": 0,
              "ets_price_eur": ets_price_eur, "eur_krw": eur_krw}

    direct = ghg_all.get("ghg_regional_direct", {})
    gas_sector = ghg_all.get("ghg_gas_sector", {})

    direct_rows   = direct.get("data", [])
    gs_rows       = gas_sector.get("data", [])
    latest_direct = direct.get("latest_year")
    latest_gs     = gas_sector.get("latest_year")

    if not direct_rows or not gs_rows:
        result["error"] = "데이터 미수집"
        return result

    # ── CO₂ 분야별 비율 산출 (전국 기준) ──
    co2_sector_total = {}   # {분야코드: CO₂량}
    co2_all_total    = 0
    for row in gs_rows:
        if row.get("PRD_DE") != latest_gs: continue
        if "CO₂" not in (row.get("C1_NM","") or "") and "CO2" not in (row.get("C1_NM","") or ""):
            continue
        sector = row.get("C2_NM","") or row.get("C2","")
        val    = _float(row.get("DT"))
        if val and sector:
            co2_sector_total[sector] = co2_sector_total.get(sector, 0) + val
            co2_all_total += val

    co2_ratio = {s: v/co2_all_total for s,v in co2_sector_total.items()} if co2_all_total else {}

    # ── 시도별 직접배출 × CO₂ 비율 → CBAM 노출액 ──
    region_totals = {}
    for row in direct_rows:
        if row.get("PRD_DE") != latest_direct: continue
        region = row.get("C1_NM","") or row.get("C1","")
        sector = row.get("C2_NM","") or row.get("C2","")
        val_gg = _float(row.get("DT"))
        if not region or not val_gg: continue
        if region not in region_totals:
            region_totals[region] = {"total_gg": 0, "by_sector": {}, "co2_gg": 0}
        region_totals[region]["total_gg"] += val_gg
        region_totals[region]["by_sector"][sector] = val_gg
        # CO₂ 추정
        r = co2_ratio.get(sector, 0.85)   # 기본 85% (에너지 기준)
        region_totals[region]["co2_gg"] += val_gg * r

    # ── CBAM 노출액 계산 ──
    for region, vals in region_totals.items():
        co2_t     = vals["co2_gg"] * 1000   # Gg → kt → ×1000 = t
        exposure  = co2_t * ets_price_eur * eur_krw / 1e8  # 억원
        result["regions"][region] = {
            "total_gg":         round(vals["total_gg"], 2),
            "co2_estimated_gg": round(vals["co2_gg"], 2),
            "co2_tonne":        round(co2_t, 0),
            "cbam_exposure_억원": round(exposure, 1),
            "cert_needed_tCO2":   round(co2_t, 0),
            "by_sector":        vals["by_sector"],
            "year":             latest_direct,
        }

    result["national_total_gg"] = sum(v["total_gg"] for v in region_totals.values())
    result["computed_at"] = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    top = sorted(result["regions"].items(), key=lambda x: x[1]["cbam_exposure_억원"], reverse=True)
    print(f"  CBAM 노출액 계산 완료: {len(top)}개 시도")
    if top:
        print(f"  → 1위: {top[0][0]} {top[0][1]['cbam_exposure_억원']:,.1f}억원")
        print(f"  → 2위: {top[1][0]} {top[1][1]['cbam_exposure_억원']:,.1f}억원" if len(top)>1 else "")

    return result


# ══════════════════════════════════════════════════════
# 두레비즈 DURE-Biz — 기업분포 카테고리
# 전국사업체조사 8종 (orgId=101, 11차개정 2020~)
# 출처: 국가데이터처 「전국사업체조사」
# 수록: 2020~2024 (년)
# ══════════════════════════════════════════════════════

# 산업 대분류 코드 (KSIC 11차 개정)
INDUSTRY_MAP = {
    "0": "전체산업",
    "A": "농업·임업·어업",
    "B": "광업",
    "C": "제조업",           # CBAM 핵심 — 철강/화학/시멘트
    "D": "전기·가스·증기",
    "E": "수도·하수·폐기물",
    "F": "건설업",
    "G": "도매·소매업",
    "H": "운수·창고업",
    "I": "숙박·음식점업",
    "J": "정보통신업",
    "K": "금융·보험업",
    "L": "부동산업",
    "M": "전문·과학·기술",
    "N": "사업시설·임대",
    "O": "공공행정·국방",
    "P": "교육서비스업",
    "Q": "보건·사회복지",
    "R": "예술·스포츠·여가",
    "S": "협회·수리·기타",
}

# CBAM 직접 관련 업종 코드
CBAM_INDUSTRIES = {"C", "D", "E"}   # 제조업, 전기가스, 수도폐기물

BIZ_TABLES = {
    # field명: (tblId, itmId, objL3, label)
    "biz_basic":     ("DT_1K52F08", "T1+T2+T3+", "",    "시도·산업별 사업체수·종사자수·매출액"),
    "biz_by_type":   ("DT_1K52F01", "T1+T2+",    "ALL", "시도·산업·사업체구분별"),
    "biz_by_org":    ("DT_1K52F02", "T1+T2+",    "ALL", "시도·산업·조직형태별"),
    "biz_by_size":   ("DT_1K52F03", "T1+T2+",    "ALL", "시도·산업·종사자규모별"),
    "biz_by_status": ("DT_1K52F04", "T2+",        "ALL", "시도·산업·종사상지위별"),
    "biz_by_ceo_sex":("DT_1K52F05", "T1+",        "ALL", "시도·산업·대표자성별"),
    "biz_by_emp_sex":("DT_1K52F06", "T1+",        "ALL", "시도·산업·종사자성별"),
    "biz_by_ceo_age":("DT_1K52F07", "T1+",        "ALL", "시도·산업·대표자연령대별"),
}

KOSIS_BIZ_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
BIZ_INDUSTRIES = "0+A+B+C+D+E+F+G+H+I+J+K+L+M+N+O+P+Q+R+S+"


def _fetch_biz_table(key, tbl_id, itm_id, obj_l3, label):
    """전국사업체조사 단일 테이블 수집"""
    result = {"label": label, "data": [], "latest_year": None}
    params = {
        "method": "getList", "apiKey": key,
        "orgId":  "101",     "tblId":  tbl_id,
        "itmId":  itm_id,
        "objL1":  "ALL",
        "objL2":  BIZ_INDUSTRIES,
        "objL3":  obj_l3,
        "objL4": "", "objL5": "", "objL6": "", "objL7": "", "objL8": "",
        "prdSe":        "Y",
        "newEstPrdCnt": "3",
        "format": "json", "jsonVD": "Y",
    }
    try:
        r = requests.get(KOSIS_BIZ_URL, params=params, timeout=TIMEOUT)
        rows = r.json()
        if isinstance(rows, dict):
            raise RuntimeError(rows.get("errMsg") or rows.get("err") or str(rows))
        years = sorted({row.get("PRD_DE","") for row in rows if row.get("PRD_DE")}, reverse=True)
        result["latest_year"] = years[0] if years else None
        result["data"] = rows
        print(f"  BIZ [{label}] {result['latest_year']}: {len(rows)}건")
    except Exception as e:
        print(f"  BIZ [{label}] ERR: {e}")
        result["error"] = str(e)[:80]
    return result


def collect_biz_distribution(key):
    """
    전국사업체조사 8종 수집
    두레비즈 기업분포 카테고리 데이터 레이어
    """
    result = {}
    for field, (tbl_id, itm_id, obj_l3, label) in BIZ_TABLES.items():
        result[field] = _fetch_biz_table(key, tbl_id, itm_id, obj_l3, label)
        time.sleep(0.3)
    return result


def compute_cbam_industry_exposure(biz_all, ghg_regional, ets_price_eur, eur_krw):
    """
    기업분포 × 온실가스 교차 계산
    = 시도별 CBAM 대상 업종(제조업·전기가스) 기업 규모 + 배출 노출액

    입력:
      biz_all       — 전국사업체조사 수집 결과
      ghg_regional  — 지역별 온실가스 (ghg_all["ghg_regional_direct"])
      ets_price_eur — EU ETS 가격
      eur_krw       — EUR/KRW 환율

    출력: 시도별 {
      cbam_biz_count:   CBAM 대상 업종 사업체수
      cbam_emp_count:   종사자수
      cbam_revenue_억원: 매출액 (억원)
      cbam_exposure_억원: 탄소 노출액 (GHG × ETS)
      industry_breakdown: {업종코드: {사업체수, 종사자수, 매출액}}
    }
    """
    result = {"regions": {}, "computed_at": datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")}

    basic = biz_all.get("biz_basic", {})
    rows  = basic.get("data", [])
    latest = basic.get("latest_year")

    if not rows:
        result["error"] = "사업체조사 데이터 미수집"
        return result

    # ── 시도별 × 업종별 집계 ──
    region_data = {}
    for row in rows:
        if row.get("PRD_DE") != latest:
            continue
        region = row.get("C1_NM","") or row.get("C1","")
        ind    = row.get("C2","")     # 산업 코드
        ind_nm = row.get("C2_NM","") or INDUSTRY_MAP.get(ind, ind)
        itm    = row.get("ITM_ID","")
        val    = _float(row.get("DT"))

        if not region or not ind or not val:
            continue
        if region not in region_data:
            region_data[region] = {}
        if ind not in region_data[region]:
            region_data[region][ind] = {"name": ind_nm, "biz_count": 0, "emp_count": 0, "revenue_억원": 0}

        if itm == "T1":
            region_data[region][ind]["biz_count"]   += val
        elif itm == "T2":
            region_data[region][ind]["emp_count"]    += val
        elif itm == "T3":
            # T3 단위: 백만원 → 억원
            region_data[region][ind]["revenue_억원"] += val / 100

    # ── CBAM 대상 업종 필터링 + GHG 노출액 합산 ──
    ghg_rows   = ghg_regional.get("data", []) if isinstance(ghg_regional, dict) else []
    ghg_latest = ghg_regional.get("latest_year") if isinstance(ghg_regional, dict) else None

    # 시도별 직접 총배출량 (Gg → tCO₂)
    ghg_by_region = {}
    for row in ghg_rows:
        if row.get("PRD_DE") != ghg_latest:
            continue
        region = row.get("C1_NM","") or row.get("C1","")
        val    = _float(row.get("DT"))
        if region and val:
            ghg_by_region[region] = ghg_by_region.get(region, 0) + val

    for region, industries in region_data.items():
        cbam_biz = cbam_emp = cbam_rev = 0
        breakdown = {}
        for ind, vals in industries.items():
            if ind in CBAM_INDUSTRIES:
                cbam_biz += vals["biz_count"]
                cbam_emp += vals["emp_count"]
                cbam_rev += vals["revenue_억원"]
                breakdown[ind] = {
                    "name":       vals["name"],
                    "biz_count":  int(vals["biz_count"]),
                    "emp_count":  int(vals["emp_count"]),
                    "revenue_억원": round(vals["revenue_억원"], 1),
                }

        # GHG 노출액 (Gg × 1000 = t × ETS가격 × 환율)
        ghg_gg  = ghg_by_region.get(region, 0)
        exposure = ghg_gg * 1000 * ets_price_eur * eur_krw / 1e8

        result["regions"][region] = {
            "year":              latest,
            "cbam_biz_count":    int(cbam_biz),
            "cbam_emp_count":    int(cbam_emp),
            "cbam_revenue_억원": round(cbam_rev, 1),
            "cbam_exposure_억원": round(exposure, 1),
            "ghg_direct_gg":     ghg_gg,
            "industry_breakdown": breakdown,
            "all_industries":    {k: {"name":v["name"],
                                      "biz":int(v["biz_count"]),
                                      "emp":int(v["emp_count"])}
                                  for k,v in industries.items()},
        }

    top = sorted(result["regions"].items(),
                 key=lambda x: x[1]["cbam_biz_count"], reverse=True)
    print(f"  BIZ×GHG 교차계산: {len(top)}개 시도")
    if top:
        t = top[0]
        print(f"  → CBAM 업종 최다: {t[0]} "
              f"사업체 {t[1]['cbam_biz_count']:,}개 "
              f"매출 {t[1]['cbam_revenue_억원']:,.0f}억원 "
              f"탄소노출 {t[1]['cbam_exposure_억원']:,.0f}억원")
    return result


# ══════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════
def main():
    import sys
    now = datetime.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    print("=" * 52)
    print(f"외부 데이터 파이프라인 (data.go.kr 4종 + KOSIS + ECOS + NKIS): {now}")
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
    if not ECOS:
        print("⚠️  ECOS 환경변수 없음 — 거시경제지표 건너뜀")
    else:
        print(f"  ECOS키: {ECOS[:8]}...")
    if not NKIS_API_KEY:
        print("⚠️  NKIS_API_KEY 환경변수 없음 — 정책연구 건너뜀")
    else:
        print(f"  NKIS키: {NKIS_API_KEY[:8]}...")
    if not KICOX_KEY:
        print("⚠️  DATA_GO_KR 없음 — 산업단지공단 건너뜀")

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

    print("\n[⑥ ECOS 거시경제지표]")
    ext["ecos_macro"] = collect_ecos(ECOS) if ECOS else {
        "base_rate":None,"usd_krw":None,"cny_krw":None,
        "bond_3yr":None,"bond_10yr":None,"error":"ECOS 미설정"
    }

    print("\n[⑦ NKIS 정책연구]")
    ext["nkis_policy"] = collect_nkis(NKIS_API_KEY) if NKIS_API_KEY else {
        kw: [] for kw in NKIS_KEYWORDS
    }

    print("\n[⑩⑪ 두레비즈 CBAM — 온실가스 6종 + 교차계산]")
    if KOSIS:
        ext["ghg_all"] = collect_ghg_all(KOSIS)
        ext["cbam_exposure"] = compute_cbam_exposure(
            ext["ghg_all"],
            ets_price_eur=float(os.environ.get("EU_ETS_EUR","71.84")),
            eur_krw=float(os.environ.get("EUR_KRW","1485"))
        )
    else:
        ext["ghg_all"] = {k:{"label":v[2],"error":"KOSIS 미설정"} for k,v in GHG_TABLES.items()}
        ext["cbam_exposure"] = {"error":"KOSIS 미설정"}

    print("\n[⑫ 두레비즈 기업분포 — 전국사업체조사 8종]")
    if KOSIS:
        ext["biz_distribution"] = collect_biz_distribution(KOSIS)
        ext["cbam_industry"] = compute_cbam_industry_exposure(
            ext["biz_distribution"],
            ext["ghg_all"].get("ghg_regional_direct", {}),
            ets_price_eur=float(os.environ.get("EU_ETS_EUR","71.84")),
            eur_krw=float(os.environ.get("EUR_KRW","1485"))
        )
    else:
        ext["biz_distribution"] = {k:{"label":v[3],"error":"KOSIS 미설정"} for k,v in BIZ_TABLES.items()}
        ext["cbam_industry"]    = {"error":"KOSIS 미설정"}

    print("\n[⑧ KOSIS 행정구역별 인구수]")
    ext["kosis_regional_pop"] = collect_kosis_regional_pop(KOSIS) if KOSIS else {
        "data": [], "ulsan_total": None, "error": "KOSIS 미설정"
    }

    print("\n[⑨ 산업단지공단 산업동향]")
    ext["kicox_industry"] = collect_kicox(KICOX_KEY) if KICOX_KEY else {
        svc: {"label": lbl, "error": "DATA_GO_KR 미설정", "data": []}
        for svc, _, lbl in KICOX_SERVICES
    }

    if ULSAN_JSON.exists():
        try:
            u = json.loads(ULSAN_JSON.read_text(encoding="utf-8"))
            u["air_quality"] = ext["air_quality"]
            u["apt_price"]   = ext["apt_price"]
            u["bus_info"]    = ext["bus_info"]
            u["gold_price"]  = ext["gold_price"]
            u["population_forecast"] = ext["population_forecast"]
            u["ecos_macro"]          = ext["ecos_macro"]
            u["nkis_policy"]         = ext["nkis_policy"]
            u["kosis_regional_pop"]  = ext["kosis_regional_pop"]
            u["kicox_industry"]      = ext["kicox_industry"]
            u["ghg_all"]              = ext["ghg_all"]
            u["cbam_exposure"]        = ext["cbam_exposure"]
            u["biz_distribution"]     = ext["biz_distribution"]
            u["cbam_industry"]        = ext["cbam_industry"]
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
    pd_list = pf.get("data") or []
    if pd_list:
        print(f"  인구추계: {pd_list[0].get('year')}~{pd_list[-1].get('year')} "
              f"({len(pd_list)}개 연도) 최신 {pd_list[-1].get('population')}명")
    else:
        print(f"  인구추계: 데이터 없음 ({pf.get('error','')})")
    em = ext["ecos_macro"]
    print(f"  ECOS({em.get('measured_at')}): 기준금리={em.get('base_rate')}% "
          f"달러={em.get('usd_krw')} 위안={em.get('cny_krw')} "
          f"국고채3년={em.get('bond_3yr')}% 국고채10년={em.get('bond_10yr')}%")
    np = ext["nkis_policy"]
    total_nkis = sum(len(v) for v in np.values() if isinstance(v, list))
    print(f"  NKIS 정책연구: 키워드 {len(NKIS_KEYWORDS)}개 / 수집 {total_nkis}건")
    for kw, docs in np.items():
        if docs:
            print(f"    [{kw}] {docs[0].get('title','(제목없음)')} ({docs[0].get('year','')})")
    rp = ext["kosis_regional_pop"]
    print(f"  KOSIS 지역인구({rp.get('latest_period','?')}): 울산 {rp.get('ulsan_total'):,}명" if rp.get('ulsan_total') else
          f"  KOSIS 지역인구: {rp.get('error','데이터없음')}")
    ki = ext["kicox_industry"]
    kicox_ok = [v["label"] for v in ki.values() if isinstance(v, dict) and v.get("data")]
    print(f"  KICOX 산업동향: {len(kicox_ok)}종 수집 ({', '.join(kicox_ok) if kicox_ok else '없음'})")

if __name__ == "__main__":
    main()
