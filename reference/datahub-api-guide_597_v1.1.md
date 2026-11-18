# 제주데이터허브 데이터셋 API 가이드 — 597 내국인 관광객 지역·업종·성별·연령대별 카드 이용 데이터 (V1.1, 2021.09.15)

원문: `datahub-api-guide_597_v1.1.hwp` (사용자가 제주데이터허브에서 받아 첨부, 2026-11-02). 데이터 페이지: https://jejudatahub.net/data/view/data/597

## 사용 방법
1. 제주데이터허브 로그인 → 2. 사용할 데이터를 프로젝트에 담기 → 3. 마이페이지 > 프로젝트 관리 > 해당 프로젝트의 **프로젝트키**로 호출

## 요청
`https://open.jejudatahub.net/api/proxy/5D5a577taba7tbb71at1b1bt9tatata9/{your_appkey}?{params}`

공통: `number`(페이지, 기본 1), `limit`(페이지당 건수, 기본 10, 최대 100)

| 파라미터 | 설명 | 값 |
|---|---|---|
| startDate | 분석 시작월(필수) | YYYYMM |
| endDate | 분석 종료월(필수) | YYYYMM |
| sido | 시도 | |
| sigungu | 시군구 | 제주시, 서귀포시 |
| cityGubun | 도심구분 | 도심, 읍면 |
| marketType | 업종 | 교통, 기타, 소매, 쇼핑, 숙박, 유흥, 전체, 문화/레져, 식음료 |
| userType | 관광객구분 | 내국인관광객, 제주도민 |
| ageGroup | 연령대 | 20 미만, 20대, 30대, 40대, 50대, 60대이상 |
| gender | 성별 | 남, 여 |

## 응답
`{"totCnt": long, "hasMore": boolean, "data": [ {...} ]}` — 필드: sido, sigungu, cityGubun, marketType, userType, ageGroup, gender, dtYearMonth(YYYYMM), userCount, useCount, useCost
(예시 값 앞에 공백이 붙어 있음: " 제주시" → 읽을 때 앞뒤 공백 제거)
