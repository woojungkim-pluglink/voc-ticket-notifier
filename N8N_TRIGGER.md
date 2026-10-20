# n8n → GitHub Actions 트리거 (알림 주기 보장)

> Actions **내장 cron이 실제로는 하루 3~4회만 실행**되는 것을 실측으로 확인했다. n8n Schedule이 10분마다 `workflow_dispatch`를 호출해 주기를 보장한다. (n8n 도입 자체에는 코드 변경이 없었다.)

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

- Actions 내장 cron은 **notify 보조(fallback)로만 남겨 둔다**. 중복 실행은 `concurrency: voc-ticket-state`가 직렬화하므로 안전하다.
  - 폴백의 실제 힘은 약하다(2026-10-15~19 실측 **하루 0~3회**, 그중 절반이 18시 이후 지연 발화). n8n이 멈추면 SLA 20분은 지켜지지 않는다.
  - 업무시간 밖에 늦게 도착한 schedule 실행은 yml 첫 스텝 **'업무시간 가드'가 생략**시킨다(2026-10-20, 개발팀 합의 범위 준수).
  - 요약(summary)과 **야간 대기열 발송은 폴백이 없다** — 둘 다 n8n 09:00 summary 디스패치에서만 일어난다.

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

## 현재 설정 — 평일 업무시간 10분 (2026-10-15 개발팀 합의)

| | 값 |
|---|---|
| notify 트리거 | **`*/10 9-17 * * 1-5`** — KST 평일 09:00~17:50, 10분 간격 |
| summary 트리거 | `0 9 * * 1-5` — **요약의 유일한 발송원**(2026-10-15 GitHub 내장 summary 예약 제거). n8n 이 멈추면 그날 요약은 나가지 않는다 |
| n8n 버전명 | `업무시간 10분 (개발팀 합의)` (2026-10-15 10:22 발행) |

**경위**: 2026-09-09 에 24시간으로 넓혔다가(티켓 #641845 의 18시 이후 완료 알림이 3시간 늦은 사례 때문),
개발팀장이 **회사 API 서버 부하**를 지적해 업무시간으로 되돌렸다.

- 24시간 운영 시: 하루 약 150회 실행 × 1회당 API 약 60호출 = **약 9,000호출/일**, 티켓 약 57만 건 재다운로드
- 업무시간 운영 시: 평일 54회, 주말 0회
- 이 봇은 고객 앱·상담원 화면과 **같은 서버**를 쓴다. 주기를 늘릴 때는 **개발팀과 먼저 협의**한다
- 받아들인 대가: 18:00 이후 처리된 완료·취소 알림은 다음 영업일 09:00 에 발송된다
  (2026-10-20 부터 업무시간 밖 지연 cron 은 가드가 생략시키므로 '우연히 저녁에 나가는' 경우도 없다).
  신규 배분 알림은 원래 스크립트가 업무시간에만 즉시 발송하므로 영향 없다

> 2026-09-17 의 "1시간 주기로 바꿔야 한다" 지시는 **폐기**됐다. 리포를 public 으로 전환하면서 GitHub 비용 문제가 사라졌고,
> 이후 기준은 비용이 아니라 회사 API 부하다.

## 인스턴스·워크플로우 좌표 (찾는 데 시간 쓰지 말 것)

| 항목 | 값 |
|---|---|
| n8n 인스턴스 | `https://n8n.pluglink.kr` |
| 워크플로우 | `VOC 티켓 알림 트리거 (→GitHub Actions)` — ID **`bgVDfgZcJvaB86GW`** (⚠️ 2026-10-20 기준 n8n 상 실제 이름은 `10분마다 (24시간·전요일)`로 잘못 바뀌어 있다 — 이름이 아니라 ID로 찾을 것) |
| 직접 열기 | `https://n8n.pluglink.kr/workflow/bgVDfgZcJvaB86GW` |
| notify 트리거 노드 | `data-id="voc-sched-notify"` (표시 이름은 아래 주의 참조) |
| 상태 확인 (브라우저 콘솔) | `fetch('/rest/workflows/bgVDfgZcJvaB86GW', {credentials:'include', headers:{'browser-id':localStorage.getItem('n8n-browserId')}}).then(r=>r.json())` |

> 노드 표시 이름 `10분마다 (평일 09-17 KST)` 는 2026-10-15 업무시간 복귀로 **다시 실제 설정과 일치**한다.
> (2026-09-09~10-15 사이에는 라벨과 실제 cron 이 어긋나 있었다 — 판단은 항상 cron 값 기준으로.)

> ⚠️ **UI 조작 함정**: 이 n8n은 draft/publish 모델이고, Playwright의 일반 click은 캔버스 안정성 검사에서
> 타임아웃납니다. 버튼은 JS로 눌러야 합니다 —
> `document.querySelector('[data-test-id="workflow-open-publish-modal-button"]').click()` →
> 버전 이름 입력 → `[data-test-id="workflow-publish-button"]`. REST 조회에는 `browser-id` 헤더가 필요합니다.

## 스크립트 쪽 업무시간 게이트 (n8n 주기와 별개 — 혼동 주의)

n8n을 24시간으로 돌려도 **신규 배분 알림은 여전히 09:00~18:00에만 즉시 발송**됩니다.
`ticket_notifier.py`의 `is_business_hours()`(9 ≤ hour < 18)가 그 게이트이고, 코드 전체에서 **한 곳(main 의 notify 분기)**에서만 쓰입니다.

| 알림 종류 | 업무시간 게이트 | 비고 |
|---|---|---|
| **완료·취소 알림** | **없음** | 실행만 되면 시각 무관 발송. 현재는 실행 자체가 평일 업무시간뿐이라 18시 이후 처리분은 다음 영업일 09시 |
| **신규 배분 알림** | 있음 (09~18시) | 그 밖 시간에 감지되면 `overnight_queue`에 적재 → **다음 summary 실행(n8n 평일 09:00)에서만 발송**. notify 실행은 대기열을 비우지 않는다(2026-10-20 기능점검에서 코드로 확인 — 이전 서술 "다음 in-hours 실행"은 틀렸다). n8n 요약이 멈춘 날엔 대기열도 정체된다 |

`is_business_hours()`는 **요일을 보지 않습니다.** 다만 현재는 n8n·폴백 모두 평일 업무시간에만 실행되므로,
주말 배분 건은 월요일 09시 첫 실행에서 업무시간 내 감지로 **즉시 발송**됩니다(야간 대기열을 거치지 않음).
야간 신규 배분까지 즉시 알리려면 `is_business_hours()` 자체를 손봐야 하며, 이는 코드 변경 사안입니다.

## n8n 워크플로우 구성 (노드 4개)

### A. 신규 알림 트리거 (10분 주기)

**① Schedule Trigger**
- Trigger Interval: **Custom (Cron)**
- Expression: `*/10 9-17 * * 1-5`  ← **2026-10-15 개발팀 합의로 업무시간 복귀** (2026-09-09~10-15 은 `*/10 * * * *` 24시간이었음)
  - 변경 전: `*/10 9-17 * * 1-5` (KST 09:00~17:50, 평일). n8n 인스턴스 TZ는 Asia/Seoul
  - 변경 이유: 티켓 #641845가 18:02에 취소 처리됐는데 알림이 **21:13에 나갔다**(3시간 11분 지연).
    17:50이 그날 마지막 디스패치라 그 뒤 처리분을 볼 폴링이 없었고, 밀린 GitHub cron이
    21:13에 뒤늦게 터지면서 그때 감지된 것
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

- **PAT 만료 주의 — 현재 토큰 `n8n-voc-dispatch`(fine-grained) 만료 2026-12-06(일)**: 만료되면 dispatch가 401로 실패하고, 알림은 Actions 내장 cron 수준(하루 0~3회)으로 조용히 떨어지며 요약은 0회가 된다. **11/30 전에 재발급 → n8n 자격증명 `GitHub PAT — voc-ticket-notifier` 값 교체**(사람이 직접).
- **실패 알림 미연결(2026-10-20 확인)**: 이 워크플로우의 `settings.errorWorkflow`가 비어 있다. 공용 에러 워크플로우 `lhe4NxJX2N2odbKA`(→ #쿠이슬랙비서)에 연결해야 401 등 dispatch 실패가 경보로 이어진다.
- **public 리포 60일 무활동 자동 비활성**: 리포에 60일간 커밋이 없으면 GitHub가 schedule 이 있는 워크플로우를 **통째로** 비활성화한다(`disabled_inactivity`). 그러면 내장 cron 뿐 아니라 **n8n dispatch 도 거부돼 알림·요약이 전부 무음 중단**된다(추정 — dispatch 거부는 미검증).
  마지막 커밋 2026-10-20 기준 **2026-12-19 전에 커밋 1건**(문서 갱신이라도)을 넣을 것. 이미 꺼졌다면 `gh workflow enable voc-tickets.yml -R woojungkim-pluglink/voc-ticket-notifier`.
- 이 트리거가 도입되면 품질기준의 **SLA 배분 후 20분**(10분 주기 + 실행시간 ~1분)과 **요약 평일 09:00**이 실제로 달성 가능해진다.
- 되돌리기: n8n 워크플로우 비활성화 → Actions 내장 cron 폴백만 남음(하루 0~3회 notify, **요약 0회·야간 대기열 정체**).
