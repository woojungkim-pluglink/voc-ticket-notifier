# VOC 티켓 알림 자동화 — A-Z 검수 보고서

작성일 2026-07-14 · 대상 `ticket_notifier.py`(773줄) / `ticket_config.json` / `run_*.vbs` / `SETUP_GUIDE.md` / `plan.md`
방법: 6개 차원(보안·로직정확성·신뢰성·아키텍처·운영성·문서정합성) 병렬 리뷰 → 각 발견을 별도 검증자가 실제 소스와 대조하는 적대적 검증(일부는 라이브 API 샘플링까지). 54건 발견 중 **완전 반박 1건(D5)**, 나머지는 코드 사실관계 정확. 보안 주변부 일부와 D5가 심각도 하향됨.

---

## 수정 이력 (2026-07-14)

**Phase 1 — 시크릿 분리 (완료)**
- 소스 평문 비밀번호·토큰 제거 → `ticket_config.json`/환경변수 로드로 전환, 누락 시 fail-loud
- `.gitignore` + `ticket_config.example.json` 추가, SETUP_GUIDE 갱신
- ⚠️ 사용자 직접 조치 필요: 플링커넥트 비밀번호 회전 + Slack Bot Token 재발급 + 기존 `ticket_notifier.log` 정리

**Phase 2 — 로직/견고성 수정 (완료, 라이브+dry-run 검증)**
- C2: state 원자적 쓰기(`os.replace`) + `load_state` 손상 시 백업·안전 재시작
- C3: 빈/비정상 200 응답 시 스냅샷 덮어쓰기 방지(티켓 유실 차단)
- C4: 야간 대기열 발송 실패분을 큐에 되돌려 재시도(영구 유실 차단)
- C6: 채널 미초대(`not_in_channel`) 등 설정성 오류는 재시도 중단+경고(무한 재조회 차단)
- D1: 완료 판정을 `COMPLETED_STATUSES` 화이트리스트로만(중간상태 PROCESSING/MONITORING 오알림 제거)
- D2: 요약 완료집계를 종결상태 전체로 + `completedAt` 없으면 `updatedAt` 폴백(대량 누락 해소)
- D3: 스냅샷 초기화 판정을 키 존재 기반으로(0건 담당자 첫 티켓 흡수 방지)
- E4: `--dry-run` 추가(Slack 미발송·state 미변경 검증 모드)

**Phase 3 — GitHub Actions 이전 (패키지 준비 완료, 배포 대기)**
- `.github/workflows/voc-tickets.yml` + `ticket_config.ci.json` + `MIGRATION_GITHUB_ACTIONS.md` 작성, CI 런타임 모델 로컬 재현 검증 완료
- 해결: B1(SPOF)·C1(자기감시=실패 시 Slack 경보)·C7(concurrency 직렬화)·E3(로그는 Actions 보관)·시크릿(Actions Secrets)
- ⚠️ 사용자 직접: 시크릿 회전 → private repo 생성·push → Secrets 등록 → dry-run 검증 → 로컬 Task 비활성화 (절차는 MIGRATION 문서)

**남은 것(후속)**: D4(정렬 가정)·E1 잔여(TEAMS 통합)·E2(config 검증)·E5(멤버ID 정확매칭)·F계열 문서 정정. D5는 반박(무해).

---

## 총평

**기능 로직은 동작하고, 잘 설계된 부분도 있다** — 첫 실행 스냅샷 초기화로 대량발송 방지, 야간 대기열, retry 큐, 완료 스레드 알림 등. 그러나 **"타 팀이 참고·재사용할 팀 공유 운영 알림"이라는 목적**에 비추면, 코드 품질보다 세 가지 구조적 문제가 훨씬 크다:

1. **보안 — 공유하는 순간 시크릿이 유출된다** (배포 전 필수 차단)
2. **아키텍처 — 개인 PC가 단일 장애점이고, 이미 며칠간 무음 중단이 실제로 발생했다** (가장 큰 "더 나은 방향")
3. **신뢰성 — 죽어도 아무도 모른다** (자기감시 부재)

가장 중요한 결론을 먼저: **이 자동화를 개인 PC의 Task Scheduler에서 조직이 이미 운영 중인 n8n(또는 GitHub Actions)으로 옮기는 것** 하나가 위 세 문제(SPOF·시크릿·로그 로테이션·VBS 인코딩 취약성)를 동시에 해소한다. 스크립트가 표준 라이브러리(urllib)만 쓰므로 이식 비용이 낮다.

---

## 우선순위 요약 (심각도는 검증 후 보정치)

| # | 심각도 | 문제 | 조치 |
|---|--------|------|------|
| A1 | **critical** | 개인 관리자 계정 평문 비밀번호가 소스에 하드코딩 (env 폴백 없음) | 즉시 회전 + 외부화 |
| B1 | **critical** | 개인 PC 단일 장애점 — 이미 영업일 무음 중단 발생(로그 입증) | 상시가동 인프라로 이전 |
| A2 | high | 라이브 Slack Bot Token 평문 + 배포 산출물로 규정 | revoke/재발급 + 분리 |
| C1 | high | 자기감시(dead-man's switch) 없음 — 로그인 실패 시 무음 종료 | 실패 시 경보 |
| C2 | high | state 비원자적 쓰기 + 로드 예외 미처리 → 손상 시 크래시 루프 | os.replace + try/except |
| C3 | high | 빈/비정상 200 응답이 스냅샷을 리셋 → 티켓 알림 유실 | 조회 성공 명시 판정 |
| C4 | high | 야간 티켓을 발송 전 'notified' 처리 → 발송 실패 시 영구 유실 | 발송 성공 후 커밋 |
| C5 | high | 완료확인 루프가 누적 미완료 수에 비례 → 3분 제한 초과 | 배치화 + TTL |
| D1 | high | 완료 감지 catch-all(비-RECEIVED 전부 완료) → 오알림 + 진짜 완료 누락 | 화이트리스트만 |
| D2 | high | 요약 완료집계 status=COMPLETED만 → 타 종료상태 누락, completedAt null 시 0건 | 정의 통일 |
| E1/F1 | high | 담당자 설정 3곳 분산, 특히 TEAMS dict가 함수 내부 하드코딩 — 가이드 미언급 | config 통합 + 문서화 |
| C6 | medium | not_in_channel 341회 무음 재시도 무한 루프 | 설정오류는 재시도 제외+경보 |
| C7/D-lock | medium | 09:00 notify·summary가 락 없이 state 경합 → 중복 발송 | 스케줄 분리 또는 락 |
| D3 | medium | 티켓 0건 담당자의 첫 티켓이 스냅샷에 흡수 → 알림 누락 | 키 존재 기반 판정 |
| D4 | medium | createdAt 내림차순 정렬 가정 → 정렬 다르면 조기중단 누락 | 서버측 날짜필터 |
| ~~D5~~ | ~~info~~ (반박됨) | 날짜 버킷 TZ 불일치 — **활성 결함 아님**. 라이브 샘플링 결과 API가 KST-naive 반환 확인 | (향후 UTC 전환 대비 주석만) |
| E2 | medium | config 검증 부재(bare except) → 빈 설정 무음 진행 | 기동 시 엄격 검증 |
| E3 | medium | 로그 무한 append(로테이션 없음) | RotatingFileHandler |
| E5 | medium | 멤버 ID 부분매칭 + 누락 시 무음 폴백(실제 핑 안 감) | 정확매칭 + 기동검증 |
| A3 | medium | 관리자 JWT 광역 스코프(blast radius 증폭) | 서비스/스코프 계정 |
| F2 | medium | COMPLETED_STATUSES 커스터마이징 안내가 실제 로직과 모순 | 코드 수정 또는 문서 정정 |
| F3 | medium | "커밋 금지" 경고 vs 폴더에 실토큰 동봉 모순 | example 템플릿화 |
| A4 | low | Slack 봇 스코프가 문서(chat:write)보다 넓음 | channel_id 고정, 스코프 최소화 |
| A5 | low | 충전소 주소·VOC 본문 무마스킹 Slack 전송 | 링크 최소화 |
| E4 | low | 드라이런/테스트 모드 없음 | --dry-run 추가 |
| D6 | low | 담당자 간 재배분은 재알림 안 됨(정책 불명확) | 정책 명시 |
| F4 | low | 야간대기열 기능이 실제 스케줄(9-18시)에선 거의 안 탐 | 문서/스케줄 정합 |
| F5 | low | 트러블슈팅 BOM 명령이 PowerShell 5.1 전용 | PS7 호환 대안 병기 |

---

## A. 보안 — 공유 전 필수 차단

배포 목적 폴더 안에 **실제 운영 자격증명이 두 개** 들어 있다. "자산 공유 = 시크릿 공유" 구조.

- **A1 (critical)** `ticket_notifier.py:20-21`에 개인 관리자 계정(woojung.kim) 비밀번호가 평문. Slack 토큰과 달리 **환경변수 폴백조차 없어** 가장 민감한 시크릿이 오히려 소스에 고정됨. → 이미 이 검토·로그·배포 경로에 노출됐으므로 **비밀번호를 즉시 변경**하고, 개인 계정이 아닌 최소권한 전용 서비스 계정으로 전환.
- **A2 (high)** `ticket_config.json:3`에 라이브 Bot Token(`xoxb-…`). 가이드 4장이 이 파일을 "최초 배포 산출물"로 규정하는데 10장은 "시크릿 커밋 금지"라 경고 — 패키징과 문서가 모순. → 토큰 revoke/재발급, 배포본에는 `ticket_config.example.json`(빈 값)만, 폴더에 `.gitignore`(`ticket_config.json`, `ticket_state.json`, `*.log`) 추가, 코드는 `os.environ` 우선 로드.
- **A3 (medium)** 로그인이 관리자 엔드포인트라 JWT가 팀 경계를 넘는 광역 조회 권한. 그 자체가 익스플로잇은 아니나 A1 유출 시 피해 반경을 키운다.
- **A4 (low)** `conversations.list(types=public+private)` 호출은 문서가 안내한 `chat:write`보다 넓은 스코프를 요구. 실배포에선 `slack_channel_id`가 캐시돼 이 경로가 안 타므로 실害는 작음. channel_id를 고정해 폴백 자체를 제거 권장.
- **A5 (low)** 충전소 주소·VOC 본문이 마스킹 없이 채널에 전송. 단 대상은 고객 자택이 아닌 충전소 운영주소이고 수신자도 처리팀 내부 채널이라 위험은 제한적. 본문은 링크로 최소화 권장.

## B. 아키텍처 — 가장 큰 개선 방향

- **B1 (critical)** 팀 전체 알림이 개인 PC 한 대의 전원·네트워크·WSL에 100% 종속. **추측이 아니라 이미 발생함** — 로그 실행일자가 `2026-04-30` 다음 곧바로 `2026-05-08`로, 그 사이 영업일(5/4·5/7 등)에 알림이 0건 나갔고 아무도 인지 못했다. WSL DNS 실패(`Temporary failure in name resolution`) 14회, read timeout 5회도 로그에 실재.
- 4-hop 체인(Task→wscript→wsl→`bash -lc`→python)은 각 단이 독립 실패점이며, 절전/도킹 후 WSL DNS 손실이 전형적 증상.

**권고 이전 경로**

| 순위 | 방식 | 장점 | 유의 |
|------|------|------|------|
| 1 | **n8n Schedule 노드** (n8n.pluglink.kr) | 5분 주기 안정, Credentials로 시크릿 관리, static data/DB로 상태 저장(파일 손상 소멸), **실패를 기존 공용 에러 워크플로우 `lhe4NxJX2N2odbKA`로 자동 경보**(C1 동시 해결), PC 완전 이탈 | 파이썬을 노드 재작성보다 컨테이너/Execute Command로 그대로 구동하고 n8n은 스케줄+에러캐치만 맡기면 이전 비용 최소 |
| 2 | **GitHub Actions cron** (charge-test-autofill 선례) | 시크릿=Secrets, 인프라가 로그 관리 | 5분 정밀도 지연·드롭 가능, 러너 stateless라 state 영속에 마찰(cache/commit-back). **5→10~15분 SLA 완화 가능할 때만** |

이 이전 하나로 SPOF(B1)·자기감시(C1)·시크릿(A1/A2)·로그 로테이션(E3)·VBS 인코딩 취약성(온보딩)이 **동시에** 해소된다.

## C. 신뢰성 — 조용한 실패

- **C1 (high)** login() 실패 시 `sys.exit(1)`뿐, 어떤 경보도 없음. '신규 없음'과 '알리미 죽음'을 팀이 구분 못 함. 조직 공용 n8n 에러 알림이 있는데 미연동. → 정상 실행 heartbeat + N분 무실행 시 경보(dead-man's switch).
- **C2 (high)** `save_state`가 직접 덮어쓰기(원자성 없음), `load_state`엔 try/except 없음(load_config엔 있는데). 정전·wsl 종료·절전 중 쓰기가 끊기면 JSON 손상 → 매 실행 크래시 → 무음 영구 중단. 가이드의 유일한 복구법('state 삭제')은 그 순간 티켓을 삼킴. → `os.replace` 원자적 교체 + load 시 손상 백업 후 안전 재시작.
- **C3 (high)** `api_request`가 HTTPError만 잡아, 서버가 200+빈 body를 주면 예외 없이 `current_map={}` → 스냅샷을 `[]`로 덮어씀 → 그 사이 배분된 티켓이 알림 없이 흡수. → 조회 실패를 명시 예외로 승격, 빈 응답 시 스냅샷 미갱신.
- **C4 (high)** 업무외 티켓을 `overnight_queue`에 넣으면서 **발송 전에** `notified_ids`에 등록 → 다음날 발송 실패(rate limit 등) 시 재큐잉·재시도 없이 유실되고, notify도 재감지 못함. → 발송 성공 후에만 상태 커밋.
- **C5 (high)** `check_and_notify_completions`가 미완료 티켓마다 `get_ticket_by_id`를 순차 호출(각 15s). 방치 티켓이 쌓이면 매 실행이 수십~수백 콜 → 3분 ExecutionTimeLimit 초과 → kill → 저장 실패(중복/유실) 또는 스킵. → 배치 상태조회, TTL, timeout 단축.
- **C6 (medium)** 봇이 채널 밖일 때 완료 스레드가 `not_in_channel`로 **341회** 조용히 실패, 성공 시에만 completed_ids에 넣으므로 동일 11건을 매 5분 무한 재조회. → 설정오류성 에러는 재시도 제외 + 1회 경보.
- **C7 (medium, D와 중복)** 09:00에 notify·summary가 락 없이 같은 state를 read-modify-write → last-write-wins로 중복 발송. (크래시까진 아님 — read/write가 시간상 분리돼 torn read는 사실상 없음.) → summary를 08:55/09:02로 분리하거나 단일 순차 실행 병합.

## D. 로직 정확성

- **D1 (high)** `if status in COMPLETED_STATUSES or (status and status != "RECEIVED")` — 두 번째 절이 집합을 무력화. 중간상태(IN_PROGRESS 등)도 '완료'로 스레드 달고 completed_ids 등록 → 진짜 완료 시엔 이미 처리돼 재알림 없음. → catch-all 제거, 화이트리스트만.
- **D2 (high)** 요약 완료집계는 `status="COMPLETED"`만 조회하는데 완료 정의는 CLOSED/DONE/CANCELED까지 포함 → CANCELED 종료분이 '완료 0건'으로 표시. `completedAt`이 비면(코드가 `updatedAt or completedAt`로 폴백하는 것으로 보아 존재) startswith 필터가 전부 탈락. → 완료 정의를 헬퍼 하나로 통일, 날짜는 updatedAt 폴백.
- **D3 (medium)** 티켓 0건 담당자는 스냅샷이 빈 리스트라 매번 '첫 실행' 분기 → 첫 티켓이 알림 없이 흡수. → `if nickname not in employee_snapshot`처럼 키 존재로 판정.
- **D4 (medium)** 요약 신규집계가 `ca < date_str`로 조기 stop — createdAt 내림차순 가정. 정렬이 다르면 누락. 페이지 상한 range(1,20)=1900건도 오름차순이면 최신 티켓을 못 봄. → 서버측 날짜필터 또는 정렬 명시.
- ~~**D5**~~ **(반박됨 → info)** 날짜 버킷이 KST 문자열 vs API 타임스탬프 비교. 검증자가 실제 API를 라이브 샘플링한 결과 **API가 KST-naive 시각을 반환**(예: `createdAt "2026-06-24 15:04:05"`, Z/오프셋 없음)해 date_str(KST)과 동일 기준 → **자정 어긋남 버그는 발생하지 않음.** 남는 것은 "API 타임존을 암묵 신뢰(백엔드가 UTC로 바뀌면 취약)"라는 견고성 노트뿐. → 방어 주석만 권장.
- **D6 (low)** notified_ids가 티켓ID 전역 키라 담당자 간 재배분 시 새 담당자에게 재알림 안 됨(1000건 트림 후엔 됨 — 비일관). 정책 명시 필요.

## E. 운영성

- **E1 (high, F1과 동일)** 감시 대상이 (1) `TARGET_EMPLOYEES`(상단) (2) `send_daily_summary` **함수 내부** `TEAMS` dict(504-507) (3) config `slack_member_ids` 3곳에 분산. 특히 TEAMS는 함수 안이라 정독 전엔 발견도 어렵고, 가이드는 언급조차 안 함 → 타 팀이 TARGET_EMPLOYEES만 바꾸면 notify는 되는데 **아침 요약이 통째로 0건/오분류**. → 팀↔멤버를 config 한 곳으로 통합, 기동 시 정합성 검증.
- **E2 (medium)** `load_config`가 bare except로 삼켜 손상 JSON이면 빈 설정 무음 진행 → 토큰 사라져 전 알림 실패해도 Task는 0x0(성공)으로 찍힘. → 기동 시 필수 키 엄격 검증.
- **E3 (medium)** 로그 무한 append(현재 3.5MB), 정상 로그가 99.6%라 에러 신호가 매몰. 유일 진단수단인 tail이 무뎌짐. → RotatingFileHandler, 정상 실행은 1줄 요약.
- **E4 (medium)** notify/summary 외 모드 없음 → 매핑 확인하려면 실채널 발송. → `--dry-run`(Slack 대신 stdout, state 미변경).
- **E5 (medium)** `get_slack_mention`이 부분문자열 매칭 + member_id 누락 시 조용히 `@닉네임` 평문 반환(실제 ping 안 감). '케이'⊂'케이시' 같은 부분집합 충돌 위험. → 정확매칭 + 기동 검증.

## F. 문서-코드 정합성

- **F1 (high)** = E1. 가이드가 TEAMS dict를 누락.
- **F2 (medium)** 가이드 7장이 COMPLETED_STATUSES를 튜닝 포인트로 안내하나, D1의 catch-all 때문에 이 set을 편집해도 완료 판정이 안 바뀜(라벨에만 영향). 코드 수정 또는 문구 정정.
- **F3 (medium)** 10장 "커밋 금지" 경고 vs 폴더에 실토큰·실채널ID 동봉 모순. example 템플릿화 + 시크릿 외부화를 '권장'이 아닌 배포 전 필수 체크리스트로.
- **F4 (low)** 6장은 야간 대기열을 기능으로 설명하나, 5-5 스케줄이 09:00~18:00만 5분 구동하고 `is_business_hours()`가 `9<=h<18`이라 **대기열 적재 분기에 거의 도달 안 함**(원래 plan.md의 `*/5 9-18`은 18시대도 돌아 채워졌음). 실동작과 설명 불일치. → 스케줄 조정 또는 설명 정정.
- **F5 (low)** 8장 BOM 확인 `Get-Content -Encoding Byte`는 PowerShell 5.1 전용(PS7은 `-AsByteStream`). → `[System.IO.File]::ReadAllBytes(path)[0..1]` 병기.

---

## 권장 실행 순서

1. **지금 즉시**: A1 비밀번호 회전, A2 Bot Token 재발급 (노출 상태 해소).
2. **공유 전 필수**: 시크릿 외부화 + `.gitignore` + `*.example` 템플릿 (A1·A2·F3), E1/F1 TEAMS 통합.
3. **구조 개선(가장 큰 효과)**: n8n Schedule 노드로 이전 → B1·C1·A1·A2·E3 동시 해결. 로컬 유지가 불가피할 때만 아래 코드 패치.
4. **코드 패치(로컬 유지 시)**: C2(원자적 저장)·C3(빈 응답 방어)·C4(발송 후 커밋)·D1(완료 판정)·D2(요약 집계)를 우선, 이어 C5·C6·C7·D3~D5·E2~E5.
5. **문서**: F2·F4·F5 정정, 야간대기열 설명 정합.

> 이 보고서는 6개 차원 병렬 리뷰 + 발견별 적대적 검증(실제 소스 대조, 일부 라이브 API 샘플링)으로 작성됨. 60개 검증 에이전트 전부 완료, 완전 반박 1건(D5), 코드 인용은 모두 실재 확인. 심각도는 검증 후 보정치.
