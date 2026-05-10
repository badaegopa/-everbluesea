#!/usr/bin/env python3
"""
울산 5개 구·군(남구/동구/중구/북구/울주군) 인구·고용·복지 데이터 수집.

KOSIS / SGIS API 키는 환경변수에서 읽습니다 (절대 코드에 하드코딩 금지).
- KOSIS_API_KEY
- SGIS_CONSUMER_KEY
- SGIS_CONSUMER_SECRET

출력: data/ulsan.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

KST = timezone(timedelta(hours=9))

# 울산광역시 시군구 코드 (행정안전부/통계청 5자리 SGG 코드)
ULSAN_SGG = {
    "중구":   "31110",
    "남구":   "31140",
    "동구":   "31170",
    "북구":   "31200",
    "울주군": "31710",
}

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
SGIS_AUTH  = "https://sgisapi.kostat.go.kr/OpenAPI3/auth/authentication.do"
SGIS_STATS_POPULATION = "https://sgisapi.kostat.go.kr/OpenAPI3/stats/population.json"

# KOSIS 통계표 ID
# ★ 수정: objL1 울산 시도코드 = "31" (기존 "26"은 서울 코드였음)
KOSIS_TABLES = {
    # 주민등록인구 (행정안전부) — 울산 시도코드 31
    "population": {
        "orgId":        "101",
        "tblId":        "DT_1B040A3",
        "itmId":        "T20",
        "objL1":        "31",       # ★ 수정: 26(서울) → 31(울산)
        "prdSe":        "M",
        "newEstPrdCnt": "1",
    },
    # 고용 — 울산 전체 (objL1 ALL → 울산 시도코드로 좁힘)
    "employment": {
        "orgId":        "101",
        "tblId":        "DT_1DA7002S",
        "itmId":        "ALL",
        "objL1":        "31",       # ★ 수정: ALL → 31(울산)
        "prdSe":        "Y",
        "newEstPrdCnt": "1",
    },
    # 복지 (보건복지부) — 울산 시도코드
    "welfare": {
        "orgId":        "117",
        "tblId":        "DT_11761_N001",
        "itmId":        "ALL",
        "objL1":        "31",       # ★ 수정: ALL → 31(울산)
        "prdSe":        "Y",
        "newEstPrdCnt": "1",
    },
}


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.stderr.write(f"[fatal] missing env var: {name}\n")
        sys.exit(2)
    return v


def fetch_kosis(api_key: str, params: dict[str, str]) -> Any:
    q = {
        "method":   "getList",
        "apiKey":   api_key,
        "format":   "json",
        "jsonVD":   "Y",
        **params,
    }
    r = requests.get(KOSIS_BASE, params=q, timeout=30)
    r.raise_for_status()
    data = r.json()
    # ★ 디버깅: 응답 첫 2행 stderr 출력
    if isinstance(data, list):
        sys.stderr.write(f"[debug] kosis rows={len(data)}, sample={data[:2]}\n")
    else:
        sys.stderr.write(f"[debug] kosis response type={type(data)}: {str(data)[:200]}\n")
    return data


def filter_ulsan_rows(rows: Any) -> list[dict[str, Any]]:
    """KOSIS 응답에서 울산 5개 시군구 행만 골라낸다."""
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    sgg_codes = set(ULSAN_SGG.values())
    sgg_names = set(ULSAN_SGG.keys())
    for row in rows:
        c1 = str(row.get("C1", ""))
        c1_nm = row.get("C1_NM", "")
        if c1 in sgg_codes or any(name in c1_nm for name in sgg_names):
            out.append(row)
    return out


def sgis_token(key: str, secret: str) -> str:
    # ★ 디버깅: 인증 요청 URL 출력
    sys.stderr.write(f"[debug] SGIS auth URL: {SGIS_AUTH}\n")
    sys.stderr.write(f"[debug] consumer_key={key[:8]}...\n")
    r = requests.get(
        SGIS_AUTH,
        params={"consumer_key": key, "consumer_secret": secret},
        timeout=30,
        headers={"Accept": "application/json"},  # ★ 추가: 406 방지
    )
    sys.stderr.write(f"[debug] SGIS auth status={r.status_code}\n")
    r.raise_for_status()
    body = r.json()
    if body.get("errCd") not in (0, "0"):
        raise RuntimeError(f"SGIS auth failed: {body}")
    return body["result"]["accessToken"]


def fetch_sgis_population(token: str) -> dict[str, Any]:
    """SGIS 인구통계 — 울산(시도코드 31) 시군구별."""
    out: dict[str, Any] = {}
    for name, sgg in ULSAN_SGG.items():
        r = requests.get(
            SGIS_STATS_POPULATION,
            params={
                "accessToken": token,
                "adm_cd":      sgg,
                "low_search":  "0",
            },
            timeout=30,
            headers={"Accept": "application/json"},  # ★ 추가
        )
        try:
            r.raise_for_status()
            out[name] = r.json()
        except Exception as e:
            out[name] = {"error": str(e)}
    return out


def main() -> int:
    kosis_key = env("KOSIS_API_KEY")
    sgis_key  = env("SGIS_CONSUMER_KEY")
    sgis_sec  = env("SGIS_CONSUMER_SECRET")

    payload: dict[str, Any] = {
        "updated_at": datetime.now(KST).isoformat(),
        "region": "울산광역시",
        "districts": list(ULSAN_SGG.keys()),
        "sgg_codes": ULSAN_SGG,
        "kosis": {},
        "sgis": {},
    }

    # KOSIS — 인구/고용/복지
    for category, params in KOSIS_TABLES.items():
        try:
            raw = fetch_kosis(kosis_key, params)
            ulsan_rows = filter_ulsan_rows(raw)
            payload["kosis"][category] = {
                "rows_total":  len(raw) if isinstance(raw, list) else 0,
                "ulsan_rows":  ulsan_rows,
                "ulsan_count": len(ulsan_rows),  # ★ 추가: 확인용
            }
            sys.stderr.write(f"[ok] kosis/{category}: ulsan_rows={len(ulsan_rows)}\n")
        except Exception as e:
            payload["kosis"][category] = {"error": str(e)}
            sys.stderr.write(f"[err] kosis/{category}: {e}\n")

    # SGIS — 인구통계 (구·군별)
    try:
        token = sgis_token(sgis_key, sgis_sec)
        sys.stderr.write(f"[ok] SGIS token acquired\n")
        payload["sgis"]["population"] = fetch_sgis_population(token)
    except Exception as e:
        payload["sgis"]["population"] = {"error": str(e)}
        sys.stderr.write(f"[err] SGIS: {e}\n")

    out_path = Path(__file__).resolve().parent.parent / "data" / "ulsan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
