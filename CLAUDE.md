# ════════════════════════════════════════════════
# 공통 협업 지침 (클로드코드 필독 — 모든 작업 적용)
# 늘푸른바다 사회동역학연구소 · 청해(淸海)
# ════════════════════════════════════════════════

## ★ 최우선 규칙 — 성급한 답변·과잉 수정 금지
- 순서 엄수: 구조 파악 → 설계 확정 → 코드 반영. 확인 전 설계 금지.
- 수정 요청 시 반드시 먼저 확인: "정확히 무엇을, 어떻게 바꾸길 원하는가?"
- 요청 범위를 넘어선 추가 수정 절대 금지. 요청된 것만 정확히.

## ★ 코드 제공 방식
- 청해는 개발자가 아니다. 항상 완성된 파일로 제공.
- 터미널 한 줄씩 입력 방식 지양. 파일 단위 + 단순 실행 명령 하나로.

## ★ 검증 원칙 — 텍스트 정합성 ≠ 데이터 정합성 (2026-06-28 교훈)
AI 검증(ChatGPT·제미나이·클로드 대화)은 "문서 내부 논리·문장"만 본다.
원본 데이터와 대조하지 않으면 수치 오류를 절대 못 잡는다.

- 논문/보고서 검증은 반드시 두 층으로:
  ① 텍스트 정합성 — 논리·문장·구조 (AI 대화가 잘함)
  ② 데이터 정합성 — 본문의 모든 순위·수치를 원본 데이터(JSON/CSV)에서
     재계산해 대조 (반드시 코드로 실행. 눈으로·말로 하지 말 것)
- 제출 전 마지막 관문: "본문 숫자 ↔ 원본 데이터" 자동 대조 스크립트 실행.
- 실측/추정/하드코딩을 반드시 구분 표기. 모집단(N) 명시 필수.
- 교훈 사례: BSLI 논문 "142개국"이 실제 139개국(3국 None)이었고,
  한국 순위가 본문16위·부록41위·실측25위로 3중 불일치.
  AI 6회 검증이 못 잡음 — 원본 JSON을 안 봤기 때문.

## 작업 워크플로우 (확정)
청해(아이디어/방향) → 클로드(구조설계/명세) → 클로드코드(실행/코딩)
→ 제미나이(이미지/디자인) → 옵시디언(기록/저장)

## git 동기화 (필수)
- 작업 시작 전: git pull / 마감 시: add → commit → push
- 기기별 셸 문법:
  · 사무실PC·서버컴 (WSL): `&&` 연결, `~/` 경로
  · AI PC (PowerShell): `;` 연결, `~\` 경로 (&& 안 됨)
- 폴더 주의: ~/everbluesea (하이픈 없음, BSLI) ↔ ~/-everbluesea (하이픈, 메인)

## 데이터·분석 원칙
- 공공문서(언론·학회) 우선. 편향 데이터는 편향됨을 적시.
- 기술 문제는 최신 공법 서치 반영. 공식·기호엔 설명 필수. 도식·그래프 적극 삽입.
- 최종 판단은 중립적 관찰자 입장.

## 옵시디언 저장 루틴
"오늘 대화 저장하자" → MD 생성(파일명: 날짜-시간-순번-주요내용)
→ EOF 블록 + present_files 동시 제공 → git push 완료.

## 금지·주의
- 청해의 직업 경력·근무지 언급 금지.
- 두레에타: 공식 슬로건만 사용 — "시민들과 미래세대를 위한 한걸음"
- 처음 만나는 척 금지 — 기존 맥락 이어서 진행.

# ════════════════════════════════════════════════
# 이하: 저장소 기술 매뉴얼 (기존 내용 — 변경 없음)
# ════════════════════════════════════════════════

# 늘푸른바다 사회동역학 연구소 (Everblue Sea Institute)
> everbluesea.org | GitHub: badaegopa/-everbluesea

## 레포 구조
- index.html : 메인 (모든 JS/CSS 인라인, ~1641줄)
- nations/{region}/ : 국가 보고서 (europe/middle-east/northeast-asia/southeast-asia/south-asia/americas/climate)
- briefings/ : 금현물 브리핑 HTML
- papers/ : 논문 (nav `/papers/` 링크, index.html:411 — 브리핑 다음)
  - papers/index.html : 논문 목록 페이지
  - papers/lambda12_v9.8_ko.html : Λ¹² 사회동역학 프레임워크 v9.8 한글본 (SSRN 6509200)
  - papers/lambda11_v2.1_ko.html : Λ¹¹ 삼중좌표 프레임워크 v2.1 한글본
- tools/ : 도구

## index.html 핵심 위치
- line ~1537 : REGIONS 맵 (지역-아이콘-색상)
- line ~1547 : LABEL_MAP (파일명→한글 표시명) + parseName() 함수
- line ~1599 : 파일 필터 — startsWith("v") OR /Lambda12v\d+/i (v912/v913/… 자동 매칭)

## 파일명 규칙 (중요)
- 두 패턴 중 하나여야 목록에 표시됨:
  - (구) `v{버전}_{국가명}_{날짜}.html` — 예: `v9.12_korea_20260502.html`
  - (신) `{국가명}_Lambda12v{버전}[_접미사]_{날짜}.html` — 예: `Brazil_Lambda12v912_20260504.html`, `Maldives_Lambda12v913_GEI_20260504.html` (대문자 시작 OK)
- 위치: 반드시 `nations/{region}/` 폴더 안 (루트에 두면 자동 목록 미표시)
- 어느 패턴도 안 맞으면 목록 미표시 (예: `iran_flow_standalone.html` = iframe 전용)
- parseName(): `_Lambda12v\d+` + `_GEI` 토큰 제거 + 키 소문자화 후 LABEL_MAP 조회

## LABEL_MAP 현황 (새 보고서 추가시 여기도 추가)
- taiwan → 대만 (Taiwan)
- northkorea → 북한 (North Korea)
- northeast-asia → 동북아비교 (Northeast Asia)
- korea → 한국 (Korea)
- japan → 일본 (Japan)
- china → 중국 (China)
- south-asia-1 → 남아시아-1 (South Asia 1)
- southeast-asia-1 → 동남아비교-1 (Southeast Asia 1)
- southeast-asia-2 → 동남아비교-2 (Southeast Asia 2)
- west-europe-1 → 서유럽-1 (West Europe 1)
- south-europe-1 → 남유럽-1 (South Europe 1)
- north-europe-1 → 북유럽-1 (North Europe 1)
- east-europe-1 → 동유럽-1 (East Europe 1)
- balkans-1 → 발칸-1 (Balkans 1)
- uk → 영국 (UK)
- greece → 그리스 (Greece)
- hungary → 헝가리 (Hungary)
- bosnia → 보스니아 (Bosnia)
- cambodia → 캄보디아 (Cambodia)
- argentina → 아르헨티나 (Argentina)
- brazil → 브라질 (Brazil)
- mexico → 멕시코 (Mexico)
- latam-regional → 남북미 권역 (LatAm Regional)
- latam-2nd-series → 남북미-2차 (LatAm 2nd Series)
- latam-3rd-series → 남북미-3차 (LatAm 3rd Series)
- latam-4th-smallstates → 남북미-4차 소국 (LatAm 4th SmallStates)
- climateextinction-4nations → 기후멸절 4개국 비교 (Climate Extinction)
- maldives → 몰디브 (Maldives)
- tuvalu → 투발루 (Tuvalu)
- kiribati → 키리바시 (Kiribati)
- marshallislands → 마셜제도 (Marshall Islands)
- middleeast-regional → 중동 권역 (Middle East Regional)
- middleeast-west → 서중동-레반트마그레브 (West Middle East)
- middleeast-central → 중앙중동-GCC예멘 (Central Middle East)
- middleeast-east → 동중동-이란이라크터키 (East Middle East)

## 디자인 표준 v2.2 파스텔
- 배경: #F5F3EE / 그린: #5E9186 / 텍스트그린: #3A6A5E
- 골드: #B8850E / 카드: #FFFFFF / 보더: #DDD8CE

## 티스토리 HTML 금지사항
- var() / @import / script태그 / :root 전부 금지
- SVG에 width/height 명시 필수

## 엔진 & 논문
- Λ¹² v9.14 = v9.12(§31 ADI) + §33 BBD(거품경계역학) + §34 GEI(기후멸절지수) + §35 NCI(핵-기후복합지수) | SSRN 6632858 (IN REVIEW)
- 엔진 버전 이력: v9.12 §31 ADI(중남미 권역까지) → v9.13 §34 GEI(기후멸절 4개국) → v9.14 §33+§34+§35 통합(중동 권역부터)
- 보고서 푸터(v9.14): Engine: Λ¹²v9.14 | §33 BBD + §34 GEI + §35 NCI | SSRN 6632858 기반
