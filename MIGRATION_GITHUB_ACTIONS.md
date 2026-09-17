> # ⚠️ 현재 운영 상태 (2026-09-17) — 이 문서보다 우선
>
> **VOC 알림은 지금 GitHub Actions가 아니라 로컬 Windows 작업으로 돌고 있습니다.**
>
> | 구성요소 | 상태 |
> |---|---|
> | 로컬 `Pluglink_VOC_Notify` / `_Summary` | **Enabled** — 평일 09:00부터 5분 주기·9시간(→17:55), summary 09:00 |
> | GitHub 워크플로우 `voc-tickets.yml` | **disabled_manually** (10/1 전환 시 활성화) |
> | 리포 공개 범위 | **public** (2026-09-17 전환) — public 리포는 Actions 무제한 무료 |
> | 과거 실행 이력 | **1,548건 전부 삭제** (전환 전, 마스킹 이전 로그에 실명·사업장명이 있었음) |
> | n8n 트리거 `bgVDfgZcJvaB86GW` | 여전히 active(10분마다 dispatch 시도) — 워크플로우가 비활성이라 무효 |
>
> ## 왜 이렇게 됐나
>
> 2026-09-09에 n8n 트리거를 업무시간(54회/일)에서 24시간(144회/일)으로 넓힌 뒤
> **GitHub Actions 무료 한도(2,000분/월, 계정 전체 공유)가 8일 만에 소진**됐다.
>
> - 09-15 19:31 KST "90% 사용" 메일 → 09-16 14:11 "100% 사용" → 09-16 14:20 첫 실패
> - 실패 사유: `The job was not started because recent account payments have failed or your spending limit needs to be increased`
> - 같은 계정의 **service-init-audit·charge-test-autofill 도 동시에 중단**됨(한도는 리포별이 아니라 계정 단위)
> - VOC 알림 공백: 09-16 14:20 ~ 09-17 09:00 (약 18시간). 이 구간 실제 누락 배분은 **#645428 1건**
>
> ## 로컬 복구 시 반드시 한 일 (다음에도 동일)
>
> 로컬 `ticket_state.json`이 **2026-07-14에 멈춰 있어** 그대로 켜면 9월 티켓이 신규로 잡힌다.
> 켜기 전 상태를 '현재'로 봉합했다 — 스냅샷에 184건 흡수, 스테일 완료대기 12건 종결,
> 장애 시작(09-16 14:20) 이후 접수분만 알림 대상으로 남김. 백업 `ticket_state.json.bak-20260917`.
>
> ## public 전환으로 확인된 것 (2026-09-17 실측)
>
> - **결제 차단 상태에서도 public 리포의 Actions 는 정상 실행된다.** 워크플로우를 임시 활성화해
>   `dry_run=true` 로 디스패치한 결과 `conclusion=success` (run 35189608143, 이후 삭제).
>   즉 10/1 을 기다리지 않아도 VOC 는 언제든 GitHub 에서 돌릴 수 있다 — 남은 제약은 로컬과의 중복뿐.
> - private 리포인 `service-init-audit`·`charge-test-autofill` 은 **여전히 차단 상태**다.
>   계정 한도 리셋(10/1) 또는 지출한도 상향이 있어야 재개된다.
> - public 이므로 **60분 주기는 비용 목적이 아니라 소음 감소 목적**이 됐다. n8n 이 10분인 채여도 한도에는 무해하다.
>
> ## 로그 비식별 (public 이므로 필수)
>
> | 대상 | 조치 |
> |---|---|
> | 신규 배분·야간 대기 print | 담당자 실명·충전소명 제거, 티켓 ID만 |
> | dry-run 의 Slack/webhook 본문 덤프 | 기본 미출력. 로컬 확인은 `VOC_LOG_BODY=1` |
> | 일반(비 dry-run) 모드 | 본문 미출력 — 확인 완료 |
>
> ⚠️ 새 print 를 추가할 때 **담당자명·충전소명·Slack member ID·티켓 본문을 stdout 에 넣지 말 것.**
> 이 리포의 Actions 로그는 전 세계에 공개된다.
>
> ## 되돌릴 때 순서 (중복 발송 방지)
>
> 1. 로컬 작업 **먼저** 비활성화 (`Disable-ScheduledTask -TaskName Pluglink_VOC_*`)
> 2. **Actions 캐시 전부 삭제** — 캐시에 2026-09-16 시점 상태가 남아 있어, 그대로 켜면
>    그 사이 배분된 RECEIVED 티켓이 전부 '신규'로 잡혀 중복 발송된다(2026-09-17 로컬 복구 때 실측: 7건 중 6건이 중복).
>    캐시를 비우면 첫 실행이 스냅샷 초기화로 끝나 **알림 0건**, 그다음 실행부터 정상 감지된다.
>    `gh api "repos/OWNER/REPO/actions/caches" --jq '.actions_caches[].id' | xargs -I{} gh api -X DELETE "repos/OWNER/REPO/actions/caches/{}"`
>    (대가: `ticket_ts_map` 이 비어 전환 이전에 알림된 티켓의 완료 스레드 댓글은 달리지 않는다 — 수용 가능)
> 3. GitHub 워크플로우 활성화 (`gh api -X PUT repos/woojungkim-pluglink/voc-ticket-notifier/actions/workflows/voc-tickets.yml/enable`)
> 4. n8n 주기를 업무시간(`*/10 9-17 * * 1-5`)으로 되돌릴지 결정 — 24시간 유지 시 한도 재소진
> 5. 전환 직후 한 번은 중복/누락을 눈으로 확인
>
> 무료 한도는 다음 청구주기(통상 매월 1일)에 리셋된다.

# VOC 티켓 알림 — GitHub Actions 이전 가이드

로컬 개인 PC(Task Scheduler → WSL) 방식을 GitHub Actions cron으로 이전한다. `charge-test-autofill`과 동일한 조직 패턴을 따른다.

> **배포 완료 (2026-07-14)**: `woojungkim-pluglink/voc-ticket-notifier`(Private)에 배포·가동 중. 로컬 Task 2개(`Pluglink_VOC_Notify`/`Summary`)는 비활성화(이중 발송 방지). 검증: 러너에서 로그인 성공, 캐시 save/restore 양방향 확인, dry-run·실행 정상.
>
> **배포 중 교훈**: `gh secret set`에 값을 붙여넣을 때 개행/공백이 섞이면 `PLUGLINK_EMAIL`이 "이메일이 존재하지 않습니다"(404)로 실패한다. `-b`(PowerShell) 또는 `printf '%s' | gh secret set`(bash)로 개행 없이 설정할 것.

## 이 이전으로 해결되는 것 (AUDIT 대비)

| 검수 항목 | 로컬 방식 | GitHub Actions |
|-----------|-----------|----------------|
| **B1** 개인 PC SPOF | PC 꺼지면 무음 중단(실제 발생) | GitHub 인프라 상시가동 — PC 무관 |
| **C1** 자기감시 없음 | 로그인 실패 시 조용히 죽음 | 실패 시 워크플로우가 빨간불 + Slack 경보 스텝 |
| **C7** 09:00 notify·summary 경합 | 락 없이 동시 실행 | `concurrency` 그룹으로 직렬화 |
| **E3** 로그 무한 append | 3.6MB 로컬 로그 수동 관리 | 실행별 로그를 Actions가 ~90일 보관 |
| 시크릿 | 로컬 파일 | Actions Secrets(암호화) |
| 인코딩/VBS/WSL 취약성 | 4-hop 체인 | 제거 (ubuntu 러너에서 직접 python) |

## 구조

- **워크플로우**: `.github/workflows/voc-tickets.yml` (단일 파일, cron 2개)
  - notify: `*/10 0-8 * * 1-5` (KST 평일 09:00~17:50, 10분 간격)
  - summary: `0 0 * * 1-5` (KST 평일 09:00)
  - 어느 cron이 트리거했는지로 모드 자동 결정. `workflow_dispatch`로 수동 실행(모드·dry_run 선택) 가능.
- **동시성**: `concurrency: group: voc-ticket-state` — notify/summary가 절대 동시에 상태를 건드리지 않음(C7 해결).
- **상태 영속**: 러너는 stateless이므로 `ticket_state.json`을 `actions/cache` 롤링 패턴으로 복원/저장.
  - 매 실행: 최신 `voc-state-*` 복원 → 실행 → `run_id` 키로 새 캐시 저장.
  - 캐시가 없으면(최초/희귀한 eviction) 코드의 첫 실행 로직이 스냅샷만 초기화 → **대량발송 없음(안전)**.
- **설정 분리**:
  - 시크릿(`PLUGLINK_EMAIL`/`PLUGLINK_PASSWORD`/`SLACK_BOT_TOKEN`) → **Actions Secrets** (env 주입).
  - 비-시크릿(채널·멤버 매핑) → `ticket_config.ci.json`(리포에 커밋). 워크플로우가 실행 시 `ticket_config.json`으로 복사.
  - **실제 `ticket_config.json`(로컬 시크릿본)은 `.gitignore`로 리포에 안 올라감.**

## 배포 절차

> ⚠️ 굵게 표시된 단계는 **사용자 직접 수행**(GitHub 인증·시크릿 입력·비밀번호 회전은 대행 불가).

### 1. (필수, 지금) 노출된 시크릿 회전
- **플링커넥트 비밀번호 변경** (소스·로그에 노출됐음).
- **Slack Bot Token revoke/재발급** (api.slack.com/apps → OAuth & Permissions).
- 새 값은 아래 Secrets에 넣습니다(로컬 `ticket_config.json`에도 반영).

### 2. **비공개(Private) GitHub 저장소 생성 후 코드 푸시**
```bash
cd "C:/Users/user/Documents/claude/03_운영데이터/VOC-티켓전달"
git init
git add ticket_notifier.py ticket_config.ci.json ticket_config.example.json .gitignore .github SETUP_GUIDE.md AUDIT.md MIGRATION_GITHUB_ACTIONS.md plan.md
git status   # ⚠️ 커밋 전 반드시 확인: ticket_config.json / ticket_state.json / *.log 이 목록에 없어야 함
git commit -m "VOC 티켓 알림 — GitHub Actions 이전"
# GitHub에서 private repo 생성 후:
git remote add origin https://github.com/<org>/<repo>.git
git push -u origin main
```
- **저장소는 반드시 Private.** `ticket_config.ci.json`에 멤버 Slack ID가 들어 있음(비밀은 아니나 내부 정보).
- `git status`에서 `ticket_config.json`·`ticket_state.json`·`*.log`가 안 보이는지 확인(.gitignore 적용 확인).

### 3. **저장소 Settings → Secrets and variables → Actions 에 Secrets 등록**
| Secret | 값 |
|--------|-----|
| `PLUGLINK_EMAIL` | 플링커넥트 로그인 이메일(가능하면 전용 서비스 계정) |
| `PLUGLINK_PASSWORD` | 회전한 새 비밀번호 |
| `SLACK_BOT_TOKEN` | 재발급한 새 봇 토큰 |
| `VOC_ALERT_TARGET` | (선택) 실행 실패 경보 받을 채널ID 또는 DM 사용자ID. 미설정 시 경보 스킵 |

### 4. **수동 dry-run으로 검증**
- Actions 탭 → voc-tickets → Run workflow → mode=`notify`, dry_run=`true` 실행.
- 로그에 `[DRY-RUN] slack chat.postMessage: ...`가 찍히고 실제 발송이 없는지 확인.
- 이어 mode=`summary`, dry_run=`true`도 확인.

### 5. **실제 가동 확인**
- dry_run=`false`로 notify 1회 수동 실행 → Slack 채널 확인. 이후 스케줄이 자동 구동.
- 로컬 Task(`Pluglink_VOC_Notify`/`Pluglink_VOC_Summary`)는 **비활성화 또는 삭제**(이중 발송 방지):
  ```powershell
  Disable-ScheduledTask -TaskName "Pluglink_VOC_Notify"
  Disable-ScheduledTask -TaskName "Pluglink_VOC_Summary"
  ```

## 트레이드오프 (정직하게)

- **스케줄 정밀도**: Actions 스케줄은 부하 시 수~십수 분 지연되거나 드롭될 수 있음. 5분→10분으로 완화했으나 "정확히 10분"은 보장 안 됨. 분 단위 SLA가 엄격하면 상시가동 서버 + system cron(또는 n8n)이 더 적합.
- **캐시 상태**: `actions/cache`는 7일 미사용 시 eviction. 이 잡은 상시 구동이라 실질 위험은 낮지만, eviction 시 그 창에 배분된 티켓 1건이 알림 없이 흡수될 수 있음(재초기화). 더 강한 durability가 필요하면 아래 대안.
- **대안(상태 durability↑)**: `actions/cache` 대신 `ticket_state.json`을 전용 브랜치나 gist에 commit-back. 감사·durability는 좋으나 커밋 노이즈/쓰기 권한 필요. 현재는 단순성을 우선해 cache 채택.

## 참고
- 의존성 없음(표준 라이브러리만) → `pip install` 불필요.
- 코드 변경 없이 그대로 이식(Phase 1에서 env 폴백을 이미 심어둠).
- 로컬 방식 상세는 `SETUP_GUIDE.md`, 전체 검수는 `AUDIT.md` 참조.
