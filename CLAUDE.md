# 늘푸른바다 사회동역학 연구소 (Everblue Sea Institute)
> everbluesea.org | GitHub: badaegopa/-everbluesea

## 레포 구조
- index.html : 메인 (모든 JS/CSS 인라인, ~1671줄)
- nations/{region}/ : 국가 보고서 (europe/middle-east/northeast-asia/southeast-asia/south-asia/americas)
- briefings/ : 금현물 브리핑 HTML
- papers/ : 논문
- tools/ : 도구

## index.html 핵심 위치
- line ~1497 : REGIONS 맵 (지역-아이콘-색상)
- line ~1507 : LABEL_MAP (파일명→한글 표시명) + parseName() 함수
- line ~1527 : 파일 필터 f.name.startsWith("v") — v로 시작해야 목록 표시

## 파일명 규칙 (중요)
- 반드시 v로 시작: v{버전}_{국가명}_{날짜}.html
- 예: v9.12_korea_20260502.html
- v로 시작 안 하면 목록 미표시 (iran_flow_standalone.html = iframe 전용)

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

## 디자인 표준 v2.2 파스텔
- 배경: #F5F3EE / 그린: #5E9186 / 텍스트그린: #3A6A5E
- 골드: #B8850E / 카드: #FFFFFF / 보더: #DDD8CE

## 티스토리 HTML 금지사항
- var() / @import / script태그 / :root 전부 금지
- SVG에 width/height 명시 필수

## 엔진 & 논문
- Λ¹² v9.12 (§31 ADI 포함) | SSRN 6632858 (IN REVIEW)
- 보고서 푸터: Engine: Λ¹²v9.12 | ADI§31포함 | SSRN6632858기반
