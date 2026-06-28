# 20260629_ENGINE_DATA_SOURCES_V1.md
# Λ¹² 엔진 데이터 소스 명세서 V1
> 작성: 2026-06-29 | 늘푸른바다 사회동역학연구소 | 청해(淸海)
> 원칙: 엔진 업그레이드/보정 없이는 이 파일 수정 금지
> 수정 시: 버전 올리고 (V2, V3...) 수정 이유 명기
> 이전 파일: 없음 (신규 발행)

---

## 핵심 원칙
```
엔진 공식  = 고정
데이터 소스 = 이 파일 기준으로 고정
수집 루틴  = 항상 같은 순서 반복
→ 편차 없음 / 재현 가능 / 학술적 객관성 확보

보고서 자동 수행 원칙:
  "국가 단독 보고서" 또는 "권역별 보고서" 요청 시
  → 데이터 수집 → 분석 → 출력 한 번에 자동 수행
  → 별도 지시 없어도 이 파일 기준으로 루틴 실행
```

---

## 수집 루틴 순서 (매번 동일하게 실행)
```
Step 1.  WDI API      → A1·A3·A4·A6·A7·A8·A11·A12
Step 2.  WGI API      → A8 (WDI와 동일 엔드포인트, 별도 지표)
Step 3.  IMF WEO API  → A4 교차검증
Step 4.  SIPRI XLSX   → A9 군사비
Step 5.  TI CPI XLSX  → A2 부패인식
Step 6.  WIPO GII CSV → A5 혁신
Step 7.  IEP GPI CSV  → A9 교차검증
Step 8.  IEA CSV      → A6·A11 교차검증
Step 9.  WTO API      → A1·A4 무역 지표 (기존 유지)
Step 10. 교차검증      → 이탈값 플래그 처리 후 η 산출
```

---

## A1 — 인프라
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | World Bank WDI | 도로포장률 (%) | `IS.ROD.PAVE.ZS` | 무료 API (무인증) |
| 1차 | World Bank WDI | 전력접근률 (%) | `EG.ELC.ACCS.ZS` | 무료 API (무인증) |
| 1차 | World Bank WDI | 인터넷이용률 (%) | `IT.NET.USER.ZS` | 무료 API (무인증) |
| 1차 | WTO API | 상품수출액 | `ITS_MTV_AX` | API키 필요 (확보됨) |
| 교차 | ITU | ICT 발전지수 | IDI | CSV 무료 다운로드 |

---

## A2 — 제도신뢰
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | Transparency International | 부패인식지수 CPI | CPI Score | XLSX 무료 (180개국) |
| 1차 | World Justice Project | 법치지수 | ROL Score | CSV 무료 (142개국) |
| 교차 | World Bank WGI | 부패통제 | `CC.EST` | 무료 API (무인증) |
| 교차 | V-Dem | 민주주의지수 | `v2x_libdem` | CSV 무료 (200개국) |

---

## A3 — 사회결속
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | World Bank WDI | 지니계수 | `SI.POV.GINI` | 무료 API (무인증) |
| 1차 | World Values Survey | 사회적 신뢰도 | Q57 | CSV 무료 |
| 교차 | SWIID | 표준화 지니 | Gini_net | CSV 무료 |

---

## A4 — 경제역량
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | IMF WEO | GDP 성장률 (%) | `NGDP_RPCH` | 무료 API |
| 1차 | World Bank WDI | GDP per capita | `NY.GDP.PCAP.KD` | 무료 API (무인증) |
| 1차 | World Bank WDI | 제조업 비중 (%) | `NV.IND.MANF.ZS` | 무료 API (무인증) |
| 1차 | WTO API | 상품수출입 | `ITS_MTV_AX/AM` | API키 필요 (확보됨) |
| 교차 | ILO ILOSTAT | 실질임금지수 | EAR_INEE_NOC_NB | 무료 API |

---

## A5 — 지식혁신
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | World Bank WDI | R&D/GDP (%) | `GB.XPD.RSDV.GD.ZS` | 무료 API (무인증) |
| 1차 | WIPO | 특허출원수 | Patent applications | CSV 무료 |
| 1차 | WIPO GII | 글로벌혁신지수 | GII Score | CSV 무료 (132개국) |
| 교차 | UNESCO UIS | 고등교육취학률 | GRAD | 무료 API |

---

## A6 — 환경지속
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | World Bank WDI | CO₂/capita | `EN.ATM.CO2E.PC` | 무료 API (무인증) |
| 1차 | Yale EPI | 환경성과지수 | EPI Score | CSV 무료 (180개국) |
| 교차 | EDGAR (EU JRC) | CO₂ 발생지기준 | CO2_pc | CSV 무료 |
| 교차 | IEA WEO Free | 재생에너지비율 | — | CSV (CC BY-NC-SA 4.0) |

---

## A7 — 인구동태 ★현재 완전 결측 → 최우선 수집 대상
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | UN WPP 2024 | 합계출산율 TFR | TFR | CSV 무료 (237개국) |
| 1차 | World Bank WDI | 고령화비율 65+ (%) | `SP.POP.65UP.TO.ZS` | 무료 API (무인증) |
| 1차 | World Bank WDI | 인구증가율 (%) | `SP.POP.GROW` | 무료 API (무인증) |
| 1차 | World Bank WDI | 순이민율 | `SM.POP.NETM` | 무료 API (무인증) |
| 교차 | UN DESA | 인구부양비 | — | CSV 무료 |

---

## A8 — 거버넌스
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | World Bank WGI | 정부효과성 | `GE.EST` | 무료 API (무인증) |
| 1차 | World Bank WGI | 규제품질 | `RQ.EST` | 무료 API (무인증) |
| 1차 | World Bank WGI | 부패통제 | `CC.EST` | 무료 API (무인증) |
| 1차 | World Bank WGI | 정치안정 | `PV.EST` | 무료 API (무인증) |
| 교차 | WJP | 법치지수 규제집행 | Factor 6 | CSV 무료 |

---

## A9 — 지정학
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | SIPRI Milex | 군사비/GDP (%) | — | XLSX 무료 (160개국) |
| 1차 | IEP GPI | 글로벌평화지수 | GPI Score | CSV 무료 (163개국) |
| 1차 | UNHCR | 난민수 | — | 무료 API |
| 교차 | World Bank WGI | 정치안정 | `PV.EST` | 무료 API (무인증) |
| 교차 | ACLED | 분쟁사건수 | — | 무료 API (등록 필요) |

---

## A10 — 문화정체
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | UNWTO | 국제관광객수 | — | CSV 무료 |
| 1차 | UNESCO | 문화수출액 | — | CSV 무료 |
| 1차 | Brand Finance | 소프트파워지수 | — | CSV 무료 (100개국) |
| 교차 | World Bank WDI | 관광객수 | `ST.INT.ARVL` | 무료 API (무인증) |

---

## A11 — 에너지
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | IEA WEO Free | 에너지자립도 | — | CSV (CC BY-NC-SA 4.0) |
| 1차 | World Bank WDI | 화석연료수입의존도 | `EG.IMP.CONS.ZS` | 무료 API (무인증) |
| 교차 | IRENA | 재생에너지비율 | — | CSV 무료 |
| 교차 | BP Statistical Review | 1차에너지소비 | — | CSV 무료 |

---

## A12 — 이동성
| 구분 | 기관 | 지표 | 코드 | 접근방식 |
|------|------|------|------|---------|
| 1차 | Henley Passport Index | 여권자유도 | Visa-free score | CSV 무료 (199개국) |
| 1차 | World Bank WDI | FDI순유입/GDP | `BX.KLT.DINV.WD.GD.ZS` | 무료 API (무인증) |
| 1차 | Freedom House | 인터넷자유도 | — | CSV 무료 |
| 교차 | UNCTAD | FDI 교차검증 | — | CSV 무료 |

---

## 교차검증 이탈값 처리 원칙
```
1차 vs 교차 편차 > 20% → 주의 플래그 🟡
1차 vs 교차 편차 > 40% → 신뢰도 "하" 플래그 🔴
단일 소스만 있는 경우  → 결측 플래그 ⬜
엔진 업그레이드 전까지 플래그 유지
하드코딩 절대 금지
```

---

## API 현황 (접근방식별)
```
✅ 무료 API 무인증 (즉시 사용):
   World Bank WDI / WGI → A1·A3·A4·A6·A7·A8·A11·A12

✅ 무료 API 인증 필요 (등록만 하면 됨):
   IMF WEO              → A4
   ILO ILOSTAT          → A4 교차
   UNESCO UIS           → A5 교차
   UNHCR                → A9
   ACLED                → A9 교차 (giseub12@gmail.com 재등록 필요)

✅ XLSX/CSV 무료 다운로드 (연 1~2회 업데이트):
   SIPRI Milex          → A9
   TI CPI               → A2
   WIPO GII             → A5
   IEP GPI              → A9 교차
   IEA WEO Free         → A6·A11
   Yale EPI             → A6
   V-Dem                → A2 교차
   Henley Passport      → A12
   Freedom House        → A12
   Brand Finance        → A10

✅ 기존 확보 API키:
   WTO API              → A1·A4 (e5769b93...)
```

---

## 청해가 해야 할 것 (순서대로)

### 1단계 — API 등록/확보 (1~2일)
```
① ACLED 재등록
   → acleddata.com → Register → giseub12@gmail.com
   → 분쟁사건 데이터 (A9 교차검증)

② IEA 계정 생성
   → iea.org → Free Dataset 다운로드
   → WEO Free Dataset CSV (CC BY-NC-SA 4.0)
   → A6 재생에너지 + A11 에너지자립도

③ SIPRI Milex 다운로드
   → sipri.org/databases/milex
   → "Share of GDP" 탭 Excel 다운로드
   → ~/everbluesea/data/external/sipri_milex_2023.xlsx

④ TI CPI 다운로드
   → transparency.org/cpi → Full data table XLSX
   → ~/everbluesea/data/external/ti_cpi_2023.xlsx

⑤ IEP GPI 다운로드
   → visionofhumanity.org/resources
   → Global Peace Index 2024 Excel
   → ~/everbluesea/data/external/iep_gpi_2023.xlsx
```

### 2단계 — Claude Code 실행 (스크립트 준비되면)
```
① WDI 수집 스크립트 실행
   → A1·A3·A4·A6·A7·A8·A11·A12 187개국 일괄 수집

② XLSX 파싱 스크립트 실행
   → SIPRI·TI·GPI → JSON 변환

③ 엔진 재산출
   → 187개국 η (V1 명세서 기준)

④ 교차검증 + 플래그 처리
```

### 3단계 — 논문 갱신
```
① η×BSLI 산점도 187국으로 갱신
② 논문 수치 일괄 업데이트
③ 한국 사분면 위치 통일
```

---

## 자동 수행 루틴 (보고서 요청 시)
```
"KOR 보고서 만들어줘" 또는 "동아시아 권역 보고서" 요청 →
  Step 1. 이 파일 기준으로 해당 국가/권역 데이터 수집
  Step 2. η 산출 (V1 공식 적용)
  Step 3. BSLI 교차
  Step 4. 괴리지수(Δ) + 사분면 배치
  Step 5. 담론육층사유법 적용
  Step 6. HTML 보고서 출력
  → 별도 지시 없이 한 번에 수행
```

---

*"있는 그대로 보여주고 문제를 찾아야지. 숨긴다고 해결 안 된다." — 청해, 2026*
