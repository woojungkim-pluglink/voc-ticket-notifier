# n8n → GitHub Actions 트리거 (알림 주기 보장)

> Actions **내장 cron이 실제로는 하루 3~4회만 실행**되는 것을 실측으로 확인했다. n8n Schedule이 10분마다 `workflow_dispatch`를 호출해 주기를 보장한다. **코드 변경은 없다.**

## 왜 필요한가 (실측 근거, 2026-09)

`voc-tickets` 스케줄 실행 100건 분석:

| | 설정 | 실측 |
|---|---|---|
| 실행 횟수 | 평일 ≈54회/일 (10분마다) | **3~4회/일** |
| 업무시간 내 | 09:00~17:50 전 구간 | **2~3회** (≈11시대, ≈16시대) |
| 최대 지연 | — | **약 4시간 50분** (11:30 배분 → 16:20 알림) |
| 일일 요약 | 평일 09:00 | **11~12시에 발송됨** (기준 위반) |

원인은 GitHub Actions의 **schedule 이벤트 throttling**(비공개·저활동 리포에서 특히 심함). 실행된 건은 100% 성공이라 겉보기엔 정상이지만, **실행 자체가 일어나지 않는 무음 지연**이다.

`workflow_dispatch`(수동/API 트리거)는 이 throttling 대상이 아니므로, 외부 스케줄러가 호출하면 주기가 지켜진다.

## 구조

```
n8n Schedule (10분/평일)  ──POST──▶  GitHub API workflow_dispatch
                                          │
                                          ▼
                                  Actions: voc-tickets.yml 실행
                                  (기존 그대로 — 상태 캐시·시크릿·경보 유지)
```

- Actions 내장 cron은 **보조(fallback)로 남겨 둔다**. n8n이 죽어도 하루 몇 번은 돌고, 중복 실행은 `concurrency: voc-ticket-state`가 직렬화하므로 안전하다.

## 준비 (1회, 직접 수행 필요)

### 1. GitHub PAT 발급
- github.com → Settings → Developer settings → **Fine-grained tokens** → Generate
- Repository access: **`voc-ticket-notifier`만** 선택
- Permissions: **Actions = Read and write** (그 외 불필요)
- 만료일 설정 후 발급 → 토큰 복사

### 2. n8n 자격증명 등록
- n8n → Credentials → **Header Auth** 생성
  - Name: `Authorization`
  - Value: `Bearer <발급한 PAT>`
- 이름 예: `GitHub PAT — voc-ticket-notifier`

> 토큰 입력은 사람이 직접 한다(에이전트가 대신 넣지 않음).

## n8n 워크플로우 구성 (노드 4개)

### A. 신규 알림 트리거 (10분 주기)

**① Schedule Trigger**
- Trigger Interval: **Custom (Cron)**
- Expression: `*/10 9-17 * * 1-5`  ← n8n 인스턴스 TZ가 **Asia/Seoul**일 때 (KST 09:00~17:50)
  - 인스턴스가 UTC면 `*/10 0-8 * * 1-5`

**② HTTP Request**
| 항목 | 값 |
|---|---|
| Method | `POST` |
| URL | `https://api.github.com/repos/woojungkim-pluglink/voc-ticket-notifier/actions/workflows/voc-tickets.yml/dispatches` |
| Authentication | Generic Credential Type → **Header Auth** (위에서 만든 것) |
| Header | `Accept: application/vnd.github+json` |
| Body Content Type | JSON |
| Body | `{"ref":"main","inputs":{"mode":"notify","dry_run":"false"}}` |

> 성공 응답은 **204 No Content**(본문 없음). n8n에서 빈 응답이 정상이다.

### B. 일일 요약 트리거 (평일 09:00)

**③ Schedule Trigger** — Cron `0 9 * * 1-5` (UTC 인스턴스면 `0 0 * * 1-5`)
**④ HTTP Request** — ②와 동일하되 Body만:
`{"ref":"main","inputs":{"mode":"summary","dry_run":"false"}}`

## 검증

1. **API 단독 테스트** (n8n 붙이기 전, 터미널에서):
   ```bash
   curl -i -X POST \
     -H "Accept: application/vnd.github+json" \
     -H "Authorization: Bearer <PAT>" \
     https://api.github.com/repos/woojungkim-pluglink/voc-ticket-notifier/actions/workflows/voc-tickets.yml/dispatches \
     -d '{"ref":"main","inputs":{"mode":"notify","dry_run":"true"}}'
   ```
   → `HTTP/2 204` 면 성공. Actions 탭에 `workflow_dispatch` 실행이 뜬다.
2. **n8n 활성화 후**: 10~20분 지켜보며 Actions 실행이 10분 간격으로 쌓이는지 확인.
3. **1주 후 재측정**: 업무시간 내 실행 횟수가 ≈54회/일에 근접하는지. 미달이면 n8n 스케줄 자체를 점검.

## 운영 메모

- **PAT 만료 주의**: 만료되면 dispatch가 401로 실패하고, 알림은 Actions 내장 cron 수준(하루 3~4회)으로 조용히 떨어진다. n8n 실행 실패 알림(공용 에러 워크플로우)에 연결해 둘 것.
- 이 트리거가 도입되면 품질기준의 **SLA 배분 후 20분**(10분 주기 + 실행시간 ~1분)과 **요약 평일 09:00**이 실제로 달성 가능해진다.
- 되돌리기: n8n 워크플로우 비활성화 → Actions 내장 cron만 남음(기존 상태).
