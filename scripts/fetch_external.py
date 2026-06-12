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
# ⑩ KOSIS 국가 온실가스 분야별 배출량 (DT_106N_99_2800020)
# ══════════════════════════════════════════════════════
# 출처: 기후에너지환경부 온실가스종합정보센터 「국가온실가스통계」
# orgId=106, tblId=DT_106N_99_2800020
# itmId=13103130539T.1100001+ (총배출량/분야별)
# 단위: 백만t CO₂eq.
# 수록기간: 1990~2023 / 자갱신일: 2026-03-31

KOSIS_GHG_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 분야 코드 매핑 (KOSIS C1 코드 → 분야명)
GHG_SECTOR_MAP = {
    "1":  "총배출량",
    "2":  "순배출량",
    "3":  "1.에너지",
    "4":  "2.산업공정및제품사용",
    "5":  "3.농업",
    "6":  "4.LULUCF",
    "7":  "5.폐기물",
}

def collect_ghg_national(key):
    """국가 온실가스 분야별 배출량 최근 3개년 수집 (단위: 백만t CO₂eq.)"""
    result = {"data": [], "latest_year": None, "total_emission": None,
              "sectors": {}, "trend": []}
    params = {
        "method":       "getList",
        "apiKey":       key,
        "orgId":        "106",
        "tblId":        "DT_106N_99_2800020",
        "itmId":        "13103130539T.1100001+",
        "objL1":        "ALL",
        "objL2":        "",
        "prdSe":        "Y",
        "newEstPrdCnt": "5",        # 최근 5개년
        "format":       "json",
        "jsonVD":       "Y",
    }
    try:
        r = requests.get(KOSIS_GHG_URL, params=params, timeout=TIMEOUT)
        rows = r.json()
        if isinstance(rows, dict):
            raise RuntimeError(rows.get("errMsg") or rows.get("err") or str(rows))

        # 연도별 분야별 정리
        data = []
        years = sorted({row.get("PRD_DE","") for row in rows if row.get("PRD_DE")}, reverse=True)
        latest = years[0] if years else None
        result["latest_year"] = latest

        # 연도별 총배출량 추세
        total_by_year = {}
        for row in rows:
            yr  = row.get("PRD_DE","")
            c1  = row.get("C1","")
            val = _float(row.get("DT"))
            if not yr or not val:
                continue
            nm = row.get("C1_NM","") or GHG_SECTOR_MAP.get(c1, c1)
            data.append({"year": yr, "sector_code": c1, "sector": nm, "value_mt": val})
            if c1 == "1":   # 총배출량
                total_by_year[yr] = val

        result["data"] = sorted(data, key=lambda x: (x["year"], x["sector_code"]), reverse=True)

        # 최신연도 분야별
        if latest:
            result["total_emission"] = total_by_year.get(latest)
            result["sectors"] = {
                row["sector"]: row["value_mt"]
                for row in data
                if row["year"] == latest
            }

        # 추세 (연도별 총배출량, 최근 5년)
        result["trend"] = [
            {"year": yr, "total_mt": total_by_year.get(yr)}
            for yr in sorted(total_by_year.keys(), reverse=True)[:5]
        ]

        print(f"  GHG 국가배출량 [{latest}] 총배출량={result['total_emission']}백만t")
        for s, v in result["sectors"].items():
            if s not in ("순배출량",):
                print(f"    └ {s}: {v}백만t")

    except Exception as e:
        print(f"  GHG 국가배출량 ERR: {e}")
        result["error"] = str(e)[:80]
    return result


# ══════════════════════════════════════════════════════
# ⑪ KOSIS 시도별 온실가스 배출량 안분 추정
# ══════════════════════════════════════════════════════
# ※ GIR 지역별 배출량은 2년 시차 공표, API 미제공
#   → 에너지사용량(KESIS) + 산업생산(KICOX) 기반 안분 계수 적용
#   → 실제 GIR 발표치와 ±15% 오차 범위 (보수적 활용 권장)

# 2021년 GIR 공표 시도별 배출량 비율 (온실가스종합정보센터 시범산정 기준)
# 출처: 한국에너지기술연구원 K-온실가스 배출 지도 (2021년 기준)
GHG_REGION_RATIO_2021 = {
    "서울":  0.0695,
    "부산":  0.0488,
    "대구":  0.0266,
    "인천":  0.0722,
    "광주":  0.0153,
    "대전":  0.0136,
    "울산":  0.0893,   # 석유화학·철강 집중으로 높음
    "세종":  0.0042,
    "경기":  0.1387,
    "강원":  0.0296,
    "충북":  0.0413,
    "충남":  0.1268,   # 화력발전 집중
    "전북":  0.0318,
    "전남":  0.0884,   # 여수 석유화학
    "경북":  0.0876,   # POSCO 포항
    "경남":  0.0622,
    "제주":  0.0113,
    # 비율 합계 ≈ 1.0
}

def collect_ghg_regional(key):
    """시도별 온실가스 배출량 추정 — 국가 총량 × 2021 GIR 비율 안분"""
    result = {"data": [], "method": "GIR_2021_RATIO", "base_year": "2021",
              "warning": "GIR 공식 발표치가 아닌 안분 추정값. ±15% 오차 범위."}
    try:
        # 최신 국가 총배출량 가져오기
        ghg_national = collect_ghg_national(key)
        latest_yr  = ghg_national.get("latest_year", "2023")
        total_mt   = ghg_national.get("total_emission")

        if not total_mt:
            raise RuntimeError("국가 총배출량 수집 실패")

        data = []
        for region, ratio in GHG_REGION_RATIO_2021.items():
            est_mt = round(total_mt * ratio, 3)
            data.append({
                "region":      region,
                "ratio_2021":  ratio,
                "estimated_mt": est_mt,
                "estimated_year": latest_yr,
                "tCO2_per_capita": None,   # 인구 데이터 연동 시 채울 수 있음
            })

        data.sort(key=lambda x: x["estimated_mt"], reverse=True)
        result["data"]           = data
        result["national_total"] = total_mt
        result["estimated_year"] = latest_yr

        top = data[0]
        print(f"  GHG 지역추정 [{latest_yr}기준] 전국={total_mt}백만t")
        print(f"  → 최다: {top['region']} {top['estimated_mt']}백만t ({top['ratio_2021']*100:.1f}%)")

    except Exception as e:
        print(f"  GHG 지역추정 ERR: {e}")
        result["error"] = str(e)[:80]
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

    print("\n[⑩ 국가 온실가스 분야별 배출량]")
    ext["ghg_national"] = collect_ghg_national(KOSIS) if KOSIS else {"data":[],"error":"KOSIS 미설정"}

    print("\n[⑪ 시도별 온실가스 배출량 추정]")
    ext["ghg_regional"] = collect_ghg_regional(KOSIS) if KOSIS else {"data":[],"error":"KOSIS 미설정"}

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
            u["ghg_national"]         = ext["ghg_national"]
            u["ghg_regional"]         = ext["ghg_regional"]
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
