# Hand-off — `voc-ticket-notifier` public 전환

- 작성 2026-09-17 · 요청자 쿠이
- **범위: public 전환 하나만.** 주기 변경(60분)·캐시 최적화·결제 해제는 이 문서 범위 밖
- 인계 사유: 60분 주기 변경을 진행 중인 세션에서 함께 처리

---

## 1. 왜 하는가

2026-09-16 Actions **지출 한도 초과로 자동화 3종 전부 중단**됐다.
(`The job was not started because recent account payments have failed or your spending limit needs to be increased`)

**31일 실측 사용량** (과금 = 잡당 분 올림, 최소 1분 / private 리포만 차감):

| 워크플로 | 실행 | 성공 평균 | 과금 추정 | 비중 |
|---|---|---|---|---|
| **voc-tickets** | 1,000회 | 85초 | **2,323분** | **84%** |
| service-init-audit | 120회 | 137초 | 375분 | 14% |
| charge-test-autofill | 60회 | 33초 | 63분 | 2% |
| 합계 | | | **2,761분** | 무료 2,000분의 **138%** |

**public 리포는 Actions가 무제한 무료**다. VOC 하나만 public으로 돌리면 계정 사용량의 84%가 한도 집계에서 빠진다.

| 시나리오 | 월 과금 |
|---|---|
| 현재(10분 주기·private) | 2,761분 (138%) ❌ |
| 60분 주기만 (private) | 약 1,878분 (94%) ⚠️ 여유 6% |
| **60분 + VOC public** | **약 438분 (22%)** ✅ |

> 60분 주기만으로도 한도 안에는 들어오지만 여유가 6%뿐이다. public 전환을 더하면 구조적으로 여유가 생긴다.

---

## 2. 보안 스캔 결과 — 전환해도 안전 (2026-09-17 실시)

작업트리 + **git 히스토리 전체(16커밋)** 를 패턴 17종으로 스캔했다.

| 항목 | 결과 |
|---|---|
| 실제 `.env`·서비스계정 키·인증서 | **없음** — 현재도, 히스토리에도 (`--diff-filter=A` 전수 확인) |
| `xoxb-YOUR-BOT-TOKEN` (ticket_config.example.json) | **자리표시자** |
| `your-account@pluglink.kr` (SETUP_GUIDE.md, example json) | **자리표시자** |
| `.gitignore` | 실제 설정파일(`ticket_config.json`, `ticket_state.json`, `es_input.json`) 정상 차단 |
| 비밀 4종 | **Secrets에만 존재** — 코드에 하드코딩 없음 |

**등록된 Secrets** (public 전환 후에도 안전, 노출되지 않음):
`SLACK_BOT_TOKEN` · `PLUGLINK_EMAIL` · `PLUGLINK_PASSWORD` · `VOC_ALERT_TARGET`

### ★ 수용해야 하는 것 하나 — 커밋 author 이메일

**전 16커밋의 author·committer가 `woojung.kim@pluglink.kr`** 이다. 추가로 히스토리의 `diag.yml`(커밋 `b0ba876`, 이후 `ca67439`에서 제거)에도 같은 주소가 한 번 남아 있다.

- **파일을 고쳐도 해결되지 않는다.** 커밋 메타데이터라 public 전환 시 커밋 목록에서 그대로 보인다.
- 지우려면 `git filter-repo` + **force push**(전 커밋 해시 변경)가 필요하다. 16커밋짜리라 기술적으론 가능하나, **지금은 주기 변경 작업과 충돌 위험이 있어 권하지 않는다.**
- **판단: 수용.** 업무용 주소이고 공문·메일로 이미 외부에 나간다. 실질 리스크는 스팸 수집 정도다.
- 신경 쓰인다면 GitHub 계정 설정에서 **Keep my email addresses private** + **Block command line pushes that expose my email** 을 켜면 *앞으로의* 커밋은 `noreply` 로 기록된다(과거 커밋은 불변).

---

## 3. 전환 전 체크리스트

- [ ] **결제/한도 먼저 해제** — https://github.com/settings/billing
      (public 전환은 *앞으로의* 사용량만 면제한다. 차단 상태 자체는 별도로 풀어야 다른 두 워크플로가 재개된다)
- [ ] 60분 주기 변경이 **커밋·푸시 완료**된 상태인지 확인 (2026-09-17 00:25 푸시 확인됨: `cron: '0 * * * *'`)
- [ ] **n8n 트리거도 60분으로 변경**했는지 확인 — 실제 주기를 만드는 것은 워크플로 내장 cron이 아니라 n8n 이다 (`N8N_TRIGGER.md`). 이게 10분인 채로 public 전환하면 사용량은 줄지 않는다(무료라 한도엔 무해하나 실행 소음이 남는다)
- [ ] 진행 중인 PR·미푸시 로컬 커밋 없는지 확인

## 4. 전환 절차

**GitHub UI** (권장 — 확인 절차가 명확)
1. https://github.com/woojungkim-pluglink/voc-ticket-notifier/settings
2. 맨 아래 **Danger Zone → Change repository visibility → Change to public**
3. 경고 확인 후 리포 이름 입력 → 전환

**또는 CLI**
```bash
gh repo edit woojungkim-pluglink/voc-ticket-notifier --visibility public --accept-visibility-change-consequences
```

### 전환 직후 권장 설정
```bash
# 외부인 이슈/위키 유입 차단 (내부 자동화 리포이므로 불필요)
gh repo edit woojungkim-pluglink/voc-ticket-notifier --enable-issues=false --enable-wiki=false
```
- 현재 `has_issues: true` 라 public 전환 시 아무나 이슈를 열 수 있다. 끄는 편이 낫다.
- Fork 0건이라 전환 전 정리할 포크는 없다.

## 5. 전환 후 확인

```bash
# ① 공개 여부
gh api /repos/woojungkim-pluglink/voc-ticket-notifier --jq '.visibility'   # → public

# ② 워크플로 정상 동작 (결제 해제 후)
gh workflow run voc-tickets --repo woojungkim-pluglink/voc-ticket-notifier -f mode=notify -f dry_run=true
gh run list --repo woojungkim-pluglink/voc-ticket-notifier --limit 3

# ③ Secrets 유지 확인 (전환해도 남아 있어야 정상)
gh secret list --repo woojungkim-pluglink/voc-ticket-notifier
```

- **성공하면 Slack 알림이 정상 발송**되는지까지 확인(dry_run=true면 미발송이니 실제 확인은 dry_run 없이).
- 이후 한 달 사용량이 실제로 빠지는지: 계정 billing 페이지의 Actions 사용량이 VOC 몫만큼 줄어야 한다.

## 6. 되돌리기

```bash
gh repo edit woojungkim-pluglink/voc-ticket-notifier --visibility private --accept-visibility-change-consequences
```
- 언제든 private 복귀 가능하다. 다만 **공개된 동안 누군가 포크·클론했다면 그 사본은 회수되지 않는다.** 비밀이 없음을 §2에서 확인했으므로 실질 피해는 없지만, 되돌림이 완전한 원복은 아니라는 점은 알고 있을 것.

---

## 7. 주의 — public 전환 시 알아둘 동작 차이

| 항목 | 변화 |
|---|---|
| Actions 요금 | **무제한 무료** (standard runner) |
| Secrets | **그대로 유지·비노출.** 단 **fork에서 온 `pull_request` 실행에는 secrets가 전달되지 않는다** — 이 리포는 `schedule` + `workflow_dispatch`만 쓰므로 영향 없음 |
| 코드·히스토리 | 전부 공개 (§2에서 비밀 없음 확인) |
| 이슈/PR | 누구나 생성 가능 → **끄기 권장** |
| Actions 로그 | 공개된다. 로그에 고객정보·티켓 본문이 찍히지 않는지 한 번 훑어볼 것 — VOC 알림 특성상 **티켓 제목·담당자가 로그에 남을 수 있다** ⚠️ |

> ⚠️ **마지막 항목은 전환 전에 꼭 확인할 것.** 실행 로그가 공개되므로, `ticket_notifier.py`가 stdout에 티켓 제목·고객명·연락처를 출력한다면 그게 전부 공개된다. Secrets보다 이쪽이 실질 리스크가 크다. 확인 후 필요하면 로그 마스킹을 먼저 적용하고 전환할 것.

---

## 8. 참고 자료

- 사용량 실측 근거: 이 문서 §1 (2026-08-17~09-17, gh API 실행 이력 집계)
- 보안 스캔: 패턴 17종(토큰·키·PII·내부호스트) × 작업트리 + 히스토리 전체
- 관련 문서: `N8N_TRIGGER.md`(실제 주기 소재), `SETUP_GUIDE.md`, `AUDIT.md`
