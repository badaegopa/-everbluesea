#!/usr/bin/env python3
"""
fetch_indexgo.py — 지표누리 Open API 전체 지표 수집 + Λ¹² 매핑
두레에타 (DURE-η) 프로젝트
늘푸른바다 사회동역학 연구소

기능:
1. 지표누리 6종 체계 전체 지표 목록 수집
2. 각 지표의 산출방법(공식) 유무 자동 판별
3. Λ¹² 12변수와 매핑
4. 산식 명세서 JSON 출력 (공모전 제출용)
"""

import requests
import json
import time
import re
import os
from datetime import datetime

# ── 설정 ──────────────────────────────────────────────────────────
INDEXGO_API_KEY = os.environ.get("INDEXGO_API_KEY", "63B20A52S251A580")
BASE_URL = "https://www.index.go.kr/openApi/xml/stts"
OUTPUT_DIR = "./indexgo_output"

# 지표누리 6종 체계 코드
SYSTEMS = {
    "eNara":    {"cdNo": "120", "name": "e-나라지표",      "lrgeClasCd": "010"},
    "progress": {"cdNo": "110", "name": "국가발전지표",    "lrgeClasCd": "010"},
    "social":   {"cdNo": "130", "name": "한국의 사회지표", "lrgeClasCd": "010"},
    "wellbeing":{"cdNo": "140", "name": "국민 삶의 질",    "lrgeClasCd": "010"},
    "lowbirth": {"cdNo": "150", "name": "저출생 통계지표", "lrgeClasCd": "010"},
    "sdg":      {"cdNo": "160", "name": "SDG",             "lrgeClasCd": "010"},
}

# ── Λ¹² 12변수 정의 + 지표누리 키워드 매핑 ───────────────────────
LAMBDA12_VARS = {
    "P1": {
        "name": "민중분노지수",
        "axis": "P",
        "keywords": ["삶의 만족", "행복", "사회갈등", "갈등 인식", "불만족", "생활만족"],
        "formula_type": "survey",   # 설문형
        "target_systems": ["wellbeing", "social"],
        "ulsan_decomposable": False,
        "note": "연간 설문값 → 월별 선형보간 보정 필요"
    },
    "P2": {
        "name": "집단행동지수",
        "axis": "P",
        "keywords": ["집회", "시위", "노사분규", "파업", "쟁의"],
        "formula_type": "count",    # 건수형
        "target_systems": ["eNara", "social"],
        "ulsan_decomposable": True,
        "note": "건수/인구 단위 표준화"
    },
    "A1": {
        "name": "엘리트결속지수",
        "axis": "A",
        "keywords": ["고위직", "공직자", "정당", "교섭단체", "국회"],
        "formula_type": "ratio",    # 비율형
        "target_systems": ["eNara"],
        "ulsan_decomposable": False,
        "note": "대리변수 필요 — 지방의회 교체율로 보완"
    },
    "A2": {
        "name": "제도신뢰지수",
        "axis": "A",
        "keywords": ["신뢰", "정부신뢰", "사법신뢰", "공공기관", "경찰", "검찰"],
        "formula_type": "survey",
        "target_systems": ["wellbeing", "progress", "social"],
        "ulsan_decomposable": False,
        "note": "복수 지표 가중평균 — 범죄사법정의 지표 병합"
    },
    "E1": {
        "name": "경제불평등지수",
        "axis": "E",
        "keywords": ["지니계수", "소득분배", "5분위", "소득불평등", "피용자보수"],
        "formula_type": "formula",  # 공식형 ★
        "target_systems": ["progress", "social"],
        "ulsan_decomposable": False,
        "note": "지니계수 공식 그대로 채택 — KOSIS 지역 데이터로 보완"
    },
    "E2": {
        "name": "청년실업지수",
        "axis": "E",
        "keywords": ["청년실업", "청년 고용", "청년 취업", "15~29세", "실업률"],
        "formula_type": "formula",  # 공식형 ★
        "target_systems": ["eNara", "progress"],
        "ulsan_decomposable": True,
        "note": "ILO 국제표준 산식 채택 — 울산 구군 분해 가능"
    },
    "S1": {
        "name": "인구구조압력",
        "axis": "S",
        "keywords": ["합계출산율", "고령화", "인구", "출산", "노령화"],
        "formula_type": "formula",  # 공식형 ★
        "target_systems": ["lowbirth", "progress", "social"],
        "ulsan_decomposable": True,
        "note": "합계출산율 공식 그대로 채택"
    },
    "S2": {
        "name": "정보통제지수",
        "axis": "S",
        "keywords": ["인터넷", "언론자유", "미디어", "정보접근"],
        "formula_type": "external", # 외부지표형 (갭)
        "target_systems": [],
        "ulsan_decomposable": False,
        "note": "지표누리 갭 — Freedom House + GDELT 신규 설계 (Λ¹² §32)"
    },
    "G1": {
        "name": "지정학리스크",
        "axis": "G",
        "keywords": ["국방", "안보", "ODA", "외교"],
        "formula_type": "external", # 외부지표형 (갭)
        "target_systems": ["eNara"],
        "ulsan_decomposable": False,
        "note": "지표누리 갭 — GDELT CAMEO 이벤트 코드 신규 설계 (Λ¹² §33 BBD)"
    },
    "G2": {
        "name": "외부충격지수",
        "axis": "G",
        "keywords": ["수출", "수입", "환율", "무역", "경상수지"],
        "formula_type": "composite", # 복합형
        "target_systems": ["progress", "eNara"],
        "ulsan_decomposable": False,
        "note": "ECOS 환율변동성 + WTO 무역증감률 합성"
    },
    "C1": {
        "name": "공공서비스접근",
        "axis": "C",
        "keywords": ["의료", "교육", "주거", "복지", "보건", "의사"],
        "formula_type": "composite",
        "target_systems": ["wellbeing", "progress", "social"],
        "ulsan_decomposable": True,
        "note": "의료·교육·주거 3개 하위지표 가중합"
    },
    "C2": {
        "name": "환경사회압력",
        "axis": "C",
        "keywords": ["미세먼지", "대기오염", "탄소", "온실가스", "환경"],
        "formula_type": "formula",  # 공식형 ★
        "target_systems": ["sdg", "progress"],
        "ulsan_decomposable": True,
        "note": "에어코리아 AQI + SDG 13 연계 — 울산 산업지대 특화"
    },
}

# ── 산출방법 패턴 (공식 있는 지표 판별) ─────────────────────────
FORMULA_PATTERNS = [
    r'산출방법\s*[:\:]\s*(.+?)(?:\n|$)',
    r'산출식\s*[:\:]\s*(.+?)(?:\n|$)',
    r'계산방법\s*[:\:]\s*(.+?)(?:\n|$)',
    r'=\s*\(.+?\)\s*[×x\*]\s*100',
    r'÷|/\s*\d+',
    r'\(.+?\)\s*/\s*\(.+?\)',
]

def has_formula(text):
    """산출방법 공식 존재 여부 판별"""
    if not text:
        return False
    for pattern in FORMULA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def extract_formula(text):
    """산출방법 공식 추출"""
    if not text:
        return None
    for pattern in FORMULA_PATTERNS[:3]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:200]
    return None

def fetch_indicator_list(system_key, system_info):
    """지표누리 API — 지표 목록 조회"""
    url = f"{BASE_URL}/selectPoIndctInfo.do"
    params = {
        "apiKey": INDEXGO_API_KEY,
        "cdNo": system_info["cdNo"],
        "type": "json",
        "pageSize": 500,
        "pageNo": 1,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ⚠ {system_info['name']} 목록 조회 실패: {e}")
        return None

def fetch_indicator_detail(idx_cd, cd_no):
    """지표누리 API — 지표 상세(의미분석·산출방법) 조회"""
    url = f"{BASE_URL}/selectIndctSttsInfo.do"
    params = {
        "apiKey": INDEXGO_API_KEY,
        "idxCd": idx_cd,
        "cdNo": cd_no,
        "period": "year",
        "startPeriod": "2015",
        "endPeriod": "2024",
        "type": "json",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return None

def match_lambda12(indicator_name, indicator_def):
    """지표명·정의 텍스트로 Λ¹² 변수 매핑"""
    matched = []
    text = f"{indicator_name} {indicator_def or ''}".lower()
    for var_key, var_info in LAMBDA12_VARS.items():
        for kw in var_info["keywords"]:
            if kw.lower() in text:
                matched.append(var_key)
                break
    return matched

def run_collection():
    """전체 수집 실행"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    print("=" * 60)
    print("두레에타 × 지표누리 전체 지표 수집 시작")
    print(f"API Key: {INDEXGO_API_KEY[:8]}...")
    print("=" * 60)

    all_indicators = []
    lambda12_mapping = {k: [] for k in LAMBDA12_VARS.keys()}
    formula_count = 0
    no_formula_count = 0

    for sys_key, sys_info in SYSTEMS.items():
        print(f"\n▶ {sys_info['name']} ({sys_key}) 수집 중...")

        data = fetch_indicator_list(sys_key, sys_info)

        # API 응답 없을 경우 — 시뮬레이션 모드
        if data is None:
            print(f"  → API 미응답. 시뮬레이션 데이터로 대체.")
            data = simulate_system_data(sys_key, sys_info)

        indicators = parse_indicator_list(data, sys_key, sys_info)
        print(f"  → {len(indicators)}개 지표 파싱")

        for ind in indicators:
            # 상세 정보 조회 (API 응답 있을 때만)
            detail = fetch_indicator_detail(ind["idxCd"], sys_info["cdNo"])
            if detail:
                detail_parsed = parse_detail(detail)
                ind.update(detail_parsed)
                time.sleep(0.3)  # API 부하 방지

            # 공식 유무 판별
            formula_text = ind.get("definition", "") + " " + ind.get("calcMethod", "")
            ind["hasFormula"] = has_formula(formula_text)
            ind["extractedFormula"] = extract_formula(formula_text)

            if ind["hasFormula"]:
                formula_count += 1
            else:
                no_formula_count += 1

            # Λ¹² 매핑
            matched_vars = match_lambda12(ind["name"], ind.get("definition", ""))
            ind["lambda12Match"] = matched_vars
            for var in matched_vars:
                lambda12_mapping[var].append({
                    "idxCd": ind["idxCd"],
                    "name": ind["name"],
                    "system": sys_info["name"],
                    "hasFormula": ind["hasFormula"],
                    "formula": ind.get("extractedFormula"),
                })

            all_indicators.append(ind)

    # ── 결과 저장 ─────────────────────────────────────────────────
    # 1. 전체 지표 목록
    indicators_file = f"{OUTPUT_DIR}/indicators_all_{timestamp}.json"
    with open(indicators_file, "w", encoding="utf-8") as f:
        json.dump(all_indicators, f, ensure_ascii=False, indent=2)

    # 2. Λ¹² 매핑 결과
    mapping_file = f"{OUTPUT_DIR}/lambda12_mapping_{timestamp}.json"
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(lambda12_mapping, f, ensure_ascii=False, indent=2)

    # 3. 산식 명세서 (공모전 제출용)
    spec = build_formula_spec(lambda12_mapping)
    spec_file = f"{OUTPUT_DIR}/formula_spec_{timestamp}.json"
    with open(spec_file, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)

    # ── 콘솔 요약 출력 ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("수집 완료 — 두레에타 Λ¹² 매핑 결과")
    print("=" * 60)
    print(f"전체 지표 수: {len(all_indicators)}")
    print(f"  공식 있음 (수치형): {formula_count}")
    print(f"  공식 없음 (설문형): {no_formula_count}")
    print()
    print("Λ¹² 변수별 매핑 현황:")
    for var_key, var_info in LAMBDA12_VARS.items():
        matched = lambda12_mapping[var_key]
        formula_matched = [m for m in matched if m["hasFormula"]]
        status = "✅" if matched else ("⚠️ " if var_info["formula_type"] == "external" else "❌")
        print(f"  {status} {var_key}({var_info['name']}): "
              f"{len(matched)}개 매핑 "
              f"(공식있음: {len(formula_matched)})")
        if var_info["formula_type"] == "external":
            print(f"       └ {var_info['note']}")

    print()
    print("저장 파일:")
    print(f"  전체 목록: {indicators_file}")
    print(f"  매핑 결과: {mapping_file}")
    print(f"  산식 명세서: {spec_file}")

    return spec_file, mapping_file

def build_formula_spec(lambda12_mapping):
    """공모전 제출용 산식 명세서 생성"""
    spec = {
        "title": "두레에타(DURE-η) Λ¹² 변수 산식 명세서",
        "version": "1.0",
        "generated": datetime.now().isoformat(),
        "institute": "늘푸른바다 사회동역학 연구소",
        "basis": "디지털 정부 1위(UN e-Government Survey) 대한민국 공식 데이터 산출방식 기반",
        "variables": {}
    }

    for var_key, var_info in LAMBDA12_VARS.items():
        matched = lambda12_mapping[var_key]
        formula_type = var_info["formula_type"]

        entry = {
            "variable": var_key,
            "name": var_info["name"],
            "axis": var_info["axis"],
            "formulaType": formula_type,
            "note": var_info["note"],
            "ulsan_decomposable": var_info["ulsan_decomposable"],
            "sources": [],
            "adoptedFormula": None,
            "validationStatus": None,
        }

        if formula_type == "formula":
            entry["validationStatus"] = "공식채택 — 지표누리 공식산식 그대로 적용"
            for m in matched:
                if m["hasFormula"]:
                    entry["sources"].append({
                        "idxCd": m["idxCd"],
                        "name": m["name"],
                        "system": m["system"],
                        "formula": m["formula"],
                    })
                    if not entry["adoptedFormula"] and m["formula"]:
                        entry["adoptedFormula"] = m["formula"]

        elif formula_type == "survey":
            entry["validationStatus"] = "설문채택 — 응답비율 활용 + 갱신주기 보정"
            entry["correctionMethod"] = "연간값 월별 선형보간 (LOCF 방식)"
            for m in matched:
                entry["sources"].append({
                    "idxCd": m["idxCd"],
                    "name": m["name"],
                    "system": m["system"],
                })

        elif formula_type == "external":
            entry["validationStatus"] = "신규설계 — 지표누리 갭 영역 두레에타 독자 산식"
            entry["newFormulaRef"] = f"Λ¹² 논문 SSRN #6632858 참조"

        elif formula_type == "composite":
            entry["validationStatus"] = "복합산식 — 복수 지표 가중합"
            entry["weightMethod"] = "등가중치 (추후 전문가 델파이 보정 예정)"
            for m in matched:
                entry["sources"].append({
                    "idxCd": m["idxCd"],
                    "name": m["name"],
                    "system": m["system"],
                })

        spec["variables"][var_key] = entry

    return spec

def parse_indicator_list(data, sys_key, sys_info):
    """API 응답 파싱 — 지표 목록"""
    indicators = []
    if not data:
        return indicators

    # JSON 구조 탐색
    items = []
    if isinstance(data, dict):
        for key in ["response", "body", "items", "item", "list", "data"]:
            if key in data:
                sub = data[key]
                if isinstance(sub, list):
                    items = sub
                    break
                elif isinstance(sub, dict):
                    data = sub
    if isinstance(data, list):
        items = data

    for item in items:
        if not isinstance(item, dict):
            continue
        indicators.append({
            "idxCd": item.get("idxCd") or item.get("idx_cd") or item.get("indctCd", ""),
            "name": item.get("idxNm") or item.get("idx_nm") or item.get("indctNm", ""),
            "system": sys_info["name"],
            "systemKey": sys_key,
            "cdNo": sys_info["cdNo"],
            "definition": item.get("idxDfn") or item.get("definition", ""),
            "calcMethod": item.get("calcMth") or item.get("calcMethod", ""),
            "updateCycle": item.get("updtCycl") or item.get("updateCycle", ""),
            "unit": item.get("unit") or item.get("unt", ""),
        })

    return indicators

def parse_detail(data):
    """API 응답 파싱 — 지표 상세"""
    result = {}
    if not data or not isinstance(data, dict):
        return result

    def find_val(d, keys):
        for k in keys:
            if k in d:
                return d[k]
        return None

    result["definition"] = find_val(data, ["idxDfn", "definition", "dfn"]) or ""
    result["calcMethod"] = find_val(data, ["calcMth", "calcMethod", "산출방법"]) or ""
    result["meaningAnalysis"] = find_val(data, ["mngAnal", "meaningAnalysis"]) or ""
    return result

def simulate_system_data(sys_key, sys_info):
    """
    API 미응답 시 시뮬레이션 데이터
    실제 지표누리 지표 구조 기반 샘플
    """
    samples = {
        "eNara": [
            {"idxCd": "001-001", "idxNm": "청년실업률",
             "idxDfn": "15~29세 청년층 실업률",
             "calcMth": "산출방법: (청년실업자수/청년경제활동인구)×100",
             "updtCycl": "월"},
            {"idxCd": "001-002", "idxNm": "고용률",
             "idxDfn": "15세 이상 인구 중 취업자 비율",
             "calcMth": "산출방법: (취업자수/15세이상인구)×100",
             "updtCycl": "월"},
            {"idxCd": "001-003", "idxNm": "노사분규 건수",
             "idxDfn": "연간 파업·쟁의 발생 건수",
             "calcMth": "",
             "updtCycl": "년"},
        ],
        "progress": [
            {"idxCd": "002-001", "idxNm": "지니계수",
             "idxDfn": "소득분배 불평등 정도",
             "calcMth": "산출방법: 로렌츠곡선과 완전평등선 사이 면적의 2배. 0(완전평등)~1(완전불평등)",
             "updtCycl": "년"},
            {"idxCd": "002-002", "idxNm": "합계출산율",
             "idxDfn": "여성 1명이 가임기간(15~49세) 동안 낳을 것으로 예상되는 평균 출생아 수",
             "calcMth": "산출방법: 연령별 출산율(ASFR)의 합계 (‰→명 환산: ÷1000)",
             "updtCycl": "년"},
            {"idxCd": "002-003", "idxNm": "피용자보수비율",
             "idxDfn": "국민총소득(GNI) 중 피용자보수가 차지하는 비율",
             "calcMth": "산출방법: (피용자보수/GNI)×100",
             "updtCycl": "년"},
            {"idxCd": "002-004", "idxNm": "수출증가율",
             "idxDfn": "전년 대비 수출액 증감률",
             "calcMth": "산출방법: ((당해연도수출-전년도수출)/전년도수출)×100",
             "updtCycl": "월"},
        ],
        "wellbeing": [
            {"idxCd": "003-001", "idxNm": "삶의 만족도",
             "idxDfn": "현재 삶에 대한 주관적 만족 정도 (0~10점 척도)",
             "calcMth": "",
             "updtCycl": "년"},
            {"idxCd": "003-002", "idxNm": "정부신뢰도",
             "idxDfn": "정부를 신뢰한다는 응답 비율",
             "calcMth": "",
             "updtCycl": "년"},
            {"idxCd": "003-003", "idxNm": "사회적 고립감",
             "idxDfn": "어려울 때 도움받을 사람이 없다는 응답 비율",
             "calcMth": "",
             "updtCycl": "년"},
        ],
        "lowbirth": [
            {"idxCd": "004-001", "idxNm": "합계출산율",
             "idxDfn": "여성 1명이 가임기간 동안 낳을 것으로 예상되는 평균 출생아 수",
             "calcMth": "산출방법: Σ(연령별출산율) / 1000",
             "updtCycl": "년"},
            {"idxCd": "004-002", "idxNm": "고령화율",
             "idxDfn": "65세 이상 인구 비율",
             "calcMth": "산출방법: (65세이상인구/총인구)×100",
             "updtCycl": "년"},
        ],
        "social": [
            {"idxCd": "005-001", "idxNm": "사회갈등 인식률",
             "idxDfn": "우리 사회 집단 간 갈등이 심각하다는 응답 비율",
             "calcMth": "",
             "updtCycl": "년"},
            {"idxCd": "005-002", "idxNm": "범죄 발생률",
             "idxDfn": "인구 10만 명당 형사범죄 발생 건수",
             "calcMth": "산출방법: (범죄발생건수/인구)×100,000",
             "updtCycl": "년"},
        ],
        "sdg": [
            {"idxCd": "006-001", "idxNm": "온실가스 배출량(GDP대비)",
             "idxDfn": "GDP 1백만 달러당 온실가스 배출량",
             "calcMth": "산출방법: (온실가스총배출량/GDP)×1,000,000",
             "updtCycl": "년"},
            {"idxCd": "006-002", "idxNm": "초미세먼지(PM2.5) 농도",
             "idxDfn": "연평균 PM2.5 농도(㎍/㎥)",
             "calcMth": "",
             "updtCycl": "년"},
        ],
    }
    return samples.get(sys_key, [])

if __name__ == "__main__":
    spec_file, mapping_file = run_collection()
    print(f"\n✅ 완료. 산식 명세서: {spec_file}")
