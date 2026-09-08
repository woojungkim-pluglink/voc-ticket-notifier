> **상태: 보류 (2026-09-08)** — 개발팀이 별도 ES 권한 부여에 부담을 표해, Claude Code에 이미 붙어 있는 ES MCP로 조회하는 방식으로 1차 구현했습니다(`플링비즈_VOC_일일현황.md`). 대신 "Claude 앱이 열려 있어야 실행" 제약을 받아들였습니다. 상시 실행 보장이 필요해지면 이 요청서를 그대로 사용하면 됩니다.

# [요청] ES 읽기 전용 접근 권한 (플링비즈 VOC 알림 자동화)

- 요청자: 김우중(쿠이) · 작성 2026-09-08
- 대상: 개발팀 (ES/인프라 담당)
- 데이터 등급: 🟡 내부

## 한 줄 요청

플링비즈 VOC 알림 자동화를 위해 **ES 인덱스 2개에 대한 읽기 전용(read-only) 접근**(엔드포인트 + API key)을 요청드립니다.

## 배경

플링비즈 팀에서 "**자산소유주 기준** 플링비즈 VOC만 별도 알림"을 요청했습니다. 플링비즈는 충전기가 파트너 소유라 VOC가 곧 파트너 설명 자료가 되고, 정산 협의·월 보고·계약 갱신 근거로 쓰입니다. 현재 커넥트 VOC 화면에는 자산소유주 필터가 없어 갈라낼 방법이 없습니다.

기존 VOC 알림 봇은 **담당자 배분(assignedAdminUserName)** 기준이라 소유주로 필터할 수 없습니다. 기준 필드를 **자산소유주(owner.partnerName)** 로 바꿔야 하는데, 이 필드가 우리가 쓰는 REST 경로로는 닿지 않습니다(아래 참조).

## 필요한 접근

| 항목 | 내용 |
|---|---|
| 인덱스 ① (필수) | `alias_chargers_production` — 필드 `owner.partnerName`, `station.id` |
| 인덱스 ② (권장) | `alias_tickets_production` — 필드 `targetStationId`, `status`, `createdAt`, `parentVocId` |
| 권한 | **읽기 전용**(search/aggregation만). 쓰기·삭제·매핑변경 불필요 |
| 인증 | API key 권장 (계정/비번보다 회수·회전 용이) |
| 저장 위치 | GitHub Actions Secrets (암호화). 소스·설정 파일에 평문 저장하지 않습니다 |

②는 없으면 커넥트 REST(`/v101/crms/tickets`)로 대체 가능합니다. 다만 ES로 조회하면 요청 팀의 실측 수치와 동일 기준으로 대조할 수 있어 검증이 쉽습니다.

## 사용 패턴 (부하 관점)

- 실행: **평일 09:00 1회** (일일 현황 요약)
- 쿼리: 회당 **2~3건** (terms 필터 + cardinality/terms 집계). 문서 스캔 아님
- 향후 실시간 알림을 2차로 도입할 경우 10분 주기 조회를 별도 협의 예정

실제로 쓸 쿼리는 이미 검증했습니다:

```json
// ① 자산소유주 → 충전소 매핑
GET alias_chargers_production/_search
{ "query": { "terms": { "owner.partnerName": ["플러그링크(Biz_P)", "플러그링크(Biz_H)", "한백",
    "대한송유관공사", "차지네틱스", "스칼라데이터", "타키온네트워크"] } },
  "aggs": { "by_owner": { "terms": { "field": "owner.partnerName" },
            "aggs": { "stations": { "terms": { "field": "station.id", "size": 500 } } } } }, "size": 0 }

// ② 해당 충전소의 티켓
GET alias_tickets_production/_search
{ "query": { "bool": { "filter": [
    { "range": { "createdAt": { "gte": "now-7d" } } },
    { "exists": { "field": "parentVocId" } },
    { "terms": { "targetStationId": [ ...① 결과... ] } } ] } }, "size": 0,
  "aggs": { "by_status": { "terms": { "field": "status" } } } }
```

## 왜 다른 경로로는 안 되는지 (실측 근거)

| 대안 | 결과 |
|---|---|
| 커넥트 REST `/crms/tickets`·`/crms/vocs` | 접근 가능하나 **자산소유주 필드가 없음**. 파트너 관련 필드는 `cpoName`·`assignedPartnerName`·`createdPartnerName` 뿐이고 1,091건 전수가 "플러그링크"(운영사) — 대상 소유주 7종과 **0건 일치** |
| 커넥트 백오피스 `/chargers/backoffices/stations` | 소유주 있으나 우리 봇의 헤드리스 인증으로 **HTTP 401**. 브라우저 세션 인증 필요 |
| ES `station_production` (월 스냅샷) | `station.owner_partner_name` 있으나 **최신이 2026-08-01**. 8월 이후 신규 충전소가 누락돼 **티켓 34건 미탐지**를 실측 확인. 요청 팀의 "신규 자동 반영" 요건 미충족 |
| **ES `alias_chargers_production`** | **실시간 인덱스, `owner.partnerName`(keyword) 보유. 요청 팀 실측치(203개소·776대)를 정확히 재현** ✅ |

## 검증 완료 상태

요청 팀이 ES로 산출한 기준값을 우리 쪽에서 재현했습니다(위 MCP 경로로 임시 확인):

| 항목 | 요청 팀 | 재현 | 판정 |
|---|---|---|---|
| 자산 규모 | 203개소 · 776대 | 203개소 · 776대 | 일치 |
| 한백 / 대한송유관공사 / Biz_H | 29 / 27 / 11 | 29 / 27 / 11 | 일치 |
| 차지네틱스 / 타키온 / 스칼라 | 1 / 1 / 1 | 1 / 1 / 1 | 일치 |
| 플러그링크(Biz_P) | 113 | 115 | ±2 (소유주 매핑 조회 시점 차이) |

즉 **데이터·쿼리는 검증됐고, 남은 것은 자동화 실행 환경에서의 접근 권한**입니다.

## 데이터 취급

- 읽기만 수행. 인덱스 변경 없음
- Slack에는 **집계·티켓ID·충전소명 수준**만 게시. 고객 개인정보(연락처·성명) 미출력
- 자격증명은 Actions Secrets에만 보관, 소스·로그·커밋에 남기지 않음
- 접근 후 사용 로그는 GitHub Actions 실행 이력으로 추적 가능

## 권한을 주기 어려운 경우

월 스냅샷(`station_production`)으로 대체 가능하지만 **신규 충전소가 최대 1개월 누락**됩니다(실측 34건). 요청 팀의 핵심 요건("신규 개시분 자동 반영")을 충족하지 못하므로, 그 경우 한계를 요청 팀에 명시하고 합의하겠습니다.

## 희망 일정

- 권한 발급: 협의 가능한 가장 이른 시점
- 발급 후 구현·검증: 2~3일 내 (1차는 일일 현황 요약)
