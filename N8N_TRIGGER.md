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

## ⛔ 미적용 변경 — n8n 트리거를 1시간 주기로 (2026-09-17 지시)

GitHub 워크플로우의 cron은 `0 * * * *`(매시)로 **이미 바꿨지만**, 실제 주기를 만드는 것은 n8n이다.
**n8n을 바꾸지 않으면 아무 효과가 없다.**

| | 현재 | 바꿀 값 |
|---|---|---|
| n8n notify 트리거 (`voc-sched-notify`) | `*/10 * * * *` (10분·24시간) | **`0 * * * *`** (1시간·24시간) |

- 미적용 사유: 작업 시점에 n8n 세션이 만료돼 로그인 화면으로 넘어갔고, 대신 로그인할 수 없었다.
- **이 변경 없이 GitHub 워크플로우를 다시 켜면 10분 주기가 그대로 돌아 한도를 재소진한다.**
  10/1 한도 리셋 후 복귀 순서는 `MIGRATION_GITHUB_ACTIONS.md` 상단 배너 참조.
- 바꾸는 법: 워크플로우 열기 → notify 트리거 노드 더블클릭 → Expression 필드 교체 →
  Publish 모달(버튼은 JS로 클릭해야 함, 아래 UI 함정 참조).

산정 근거: 1시간·24시간 = 24회/일 × 30일 ≈ **720분/월** (한도 2,000분). 10분·24시간은 144회/일 ≈ 4,320분/월로 8일 만에 소진됐다.

## 인스턴스·워크플로우 좌표 (찾는 데 시간 쓰지 말 것)

| 항목 | 값 |
|---|---|
| n8n 인스턴스 | `https://n8n.pluglink.kr` |
| 워크플로우 | `VOC 티켓 알림 트리거 (→GitHub Actions)` — ID **`bgVDfgZcJvaB86GW`** |
| 직접 열기 | `https://n8n.pluglink.kr/workflow/bgVDfgZcJvaB86GW` |
| notify 트리거 노드 | `data-id="voc-sched-notify"` (표시 이름은 아래 주의 참조) |
| 상태 확인 (브라우저 콘솔) | `fetch('/rest/workflows/bgVDfgZcJvaB86GW', {credentials:'include', headers:{'browser-id':localStorage.getItem('n8n-browserId')}}).then(r=>r.json())` |

> ⚠️ **노드 표시 이름이 낡았습니다.** notify 트리거의 라벨은 여전히 `10분마다 (평일 09-17 KST)`인데
> 실제 cron은 `*/10 * * * *`(24시간)입니다. 자동 리네임을 두 번 시도했으나 실패했습니다 — NDV의 `inline-edit-input`에
> 값을 넣으면 브라우저 탭 제목까지 바뀌지만 **발행 모달을 거치지 않으면 서버에 반영되지 않고**,
> NDV를 닫는 순간 되돌아갑니다. (F2는 JS로 노드를 선택한 상태에서 무동작, Playwright의
> click/dblclick은 캔버스 안정성 검사에서 타임아웃.) **사람이 화면에서 노드 선택 → F2**가 가장 빠릅니다.
> 기능에는 영향이 없으며,
> **판단 기준은 라벨이 아니라 노드 파라미터의 cron 값**입니다. 손볼 기회가 있으면 라벨도 고칠 것.

> ⚠️ **UI 조작 함정**: 이 n8n은 draft/publish 모델이고, Playwright의 일반 click은 캔버스 안정성 검사에서
> 타임아웃납니다. 버튼은 JS로 눌러야 합니다 —
> `document.querySelector('[data-test-id="workflow-open-publish-modal-button"]').click()` →
> 버전 이름 입력 → `[data-test-id="workflow-publish-button"]`. REST 조회에는 `browser-id` 헤더가 필요합니다.

## 스크립트 쪽 업무시간 게이트 (n8n 주기와 별개 — 혼동 주의)

n8n을 24시간으로 돌려도 **신규 배분 알림은 여전히 09:00~18:00에만 즉시 발송**됩니다.
`ticket_notifier.py`의 `is_business_hours()`(9 ≤ hour < 18)가 그 게이트이고, 코드 전체에서 **813행 한 곳**에서만 쓰입니다.

| 알림 종류 | 업무시간 게이트 | 24시간화 효과 |
|---|---|---|
| **완료·취소 알림** | **없음** | ✅ 시각 무관 10분 내 발송 — 위 3시간 지연 사례가 해소되는 지점 |
| **신규 배분 알림** | 있음 (09~18시) | ❌ 변화 없음. 그 밖 시간은 `overnight_queue`에 적재 → 다음 in-hours 실행(09시)에 발송 |

`is_business_hours()`는 **요일을 보지 않습니다.** 따라서 24시간·전요일로 바꾼 뒤부터는
**주말 09:00~18:00 배분 건이 즉시 발송**됩니다(이전에는 n8n·cron 모두 평일만이라 월요일까지 대기).
야간 신규 배분까지 즉시 알리려면 `is_business_hours()` 자체를 손봐야 하며, 이는 코드 변경 사안입니다.

## n8n 워크플로우 구성 (노드 4개)

### A. 신규 알림 트리거 (10분 주기)

**① Schedule Trigger**
- Trigger Interval: **Custom (Cron)**
- Expression: `*/10 * * * *`  ← **2026-09-09 변경: 시간·요일 제한 해제(24시간 10분 주기)**
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

- **PAT 만료 주의**: 만료되면 dispatch가 401로 실패하고, 알림은 Actions 내장 cron 수준(하루 3~4회)으로 조용히 떨어진다. n8n 실행 실패 알림(공용 에러 워크플로우)에 연결해 둘 것.
- 이 트리거가 도입되면 품질기준의 **SLA 배분 후 20분**(10분 주기 + 실행시간 ~1분)과 **요약 평일 09:00**이 실제로 달성 가능해진다.
- 되돌리기: n8n 워크플로우 비활성화 → Actions 내장 cron만 남음(기존 상태).
