# 재설계 변수 API 수집 테스트 리포트

- 생성: 2026-05-23 17:29 KST
- KOSIS 키: 보유 / ECOS 키: 없음 / data.go.kr 키: 없음
- 울산 5구군 코드: 31110 31140 31170 31200 31710

## 항목별 가용성

### ① 인구순이동률
- 소스: `KOSIS DT_1B26A01`
- 상태: **❌ 실패**
- 응답: `{"http": 200, "ok": false, "err": "20", "errMsg": "필수요청변수값이 누락되었습니다. (objL)"}`

### ② 재정자립도
- 소스: `KOSIS DT_1YL20921(정정)`
- 상태: **✅ 가용**
- 응답: `{"http": 200, "ok": true, "rows": 8, "sample": {"C1_NM": "과천시", "ITM_NM": "재정자립도(세입과목개편전)", "PRD_DE": "2026", "DT": "62.76", "UNIT_NM": "%"}}`

### ③ 1인당 GRDP
- 소스: `KOSIS 지역소득 DT_1C86`
- 상태: **✅ 가용**
- 응답: `{"http": 200, "ok": true, "rows": 4, "sample": {"C1_NM": "경기도", "ITM_NM": "1인당 지역내총생산", "PRD_DE": "2022", "DT": "39969", "UNIT_NM": "천원"}}`

### ④ 빈집률
- 소스: `KOSIS 주택총조사 (코드 미확정)`
- 상태: **❌ 실패**
- 응답: `{"http": 200, "ok": false, "err": "21", "errMsg": "해당 통계표가 존재하지 않습니다."}`

### ⑤ 응급 골든타임
- 소스: `data.go.kr 소방청`
- 상태: **⚪ 키 미설정**
- 응답: `{"ok": false, "skip": "DATA_GO_KR_API_KEY 미설정", "need": "data.go.kr 소방청 활용신청·승인 필요"}`

### ⑥ 가계부채
- 소스: `ECOS 가계신용 151Y001`
- 상태: **⚪ 키 미설정**
- 응답: `{"ok": false, "skip": "ECOS_API_KEY 미설정", "need": "ecos.bok.or.kr 발급키 필요"}`

## 요약

- ✅ 즉시 가용: 2/6 (② 재정자립도, ③ 1인당 GRDP)
- 🟡/⚪ 키 발급 필요: ECOS(ecos.bok.or.kr), data.go.kr 소방청 활용신청
- ③④ KOSIS tblId는 후보값 — 실패 시 통계표 코드 재확인 필요

## 항목별 다음 단계

| 항목 | 상태 | 조치 |
|------|------|------|
| ① 인구순이동률 | 🟡 표 존재·param 미해결 | `DT_1B26A01`은 `objL` 분류구조 동반 필요(objL1+objL2 추정). KOSIS 통계표 메타조회(`statisticsParameterData` 대신 `statisticsList.do`)로 objL 코드 확정 필요 |
| ② 재정자립도 | ✅ 가용 | **사용자 제시 `DT_1YL20711`은 오류** → 정정 코드 **`DT_1YL20921`** 사용. 단 `objL1`에 울산 5구군 코드 필터 추가 필요(현재 전국 반환) |
| ③ 1인당 GRDP | ✅ 가용 (한계) | `DT_1C86` 시도단위만 제공 → **구·군 분해 불가**. 울산 시도값(31)으로만 활용하거나 대체지표 검토 |
| ④ 빈집률 | ❌ 코드 미확정 | 후보 `DT_1JU1505`/`DT_1JU1517` 없음, `DT_1IN1502`는 총인구. 주택총조사 빈집 정확 tblId 재조사 필요 |
| ⑤ 응급 골든타임 | ⚪ 키 미설정 | data.go.kr 소방청 구급활동 OpenAPI 활용신청·승인 후 `DATA_GO_KR_API_KEY` 주입 |
| ⑥ 가계부채 | ⚪ 키 미설정 | ECOS(ecos.bok.or.kr) 인증키 발급 후 `ECOS_API_KEY` 주입. 가계신용 통계코드 `151Y001` 후보 |

> 재현: `python3 scripts/probe_redesign.py` (KOSIS 키 내장, ECOS/data.go.kr 키는 환경변수 주입)
