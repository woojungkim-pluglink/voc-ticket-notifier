# VOC 티켓 알림 자동화 설정 가이드 (타 팀 참고용)

플러그링크커넥트 티켓 시스템의 신규 배분 티켓을 Slack으로 자동 알림하고, 매일 아침 잔여 티켓을 요약하는 자동화 구성.

> **권장 배포 경로**: 이 문서는 **로컬(Windows PC + WSL + Task Scheduler)** 방식입니다. 개인 PC가 켜져 있어야만 동작하는 단일 장애점이므로, 팀 공유 알림이라면 상시가동되는 **GitHub Actions 방식([MIGRATION_GITHUB_ACTIONS.md](MIGRATION_GITHUB_ACTIONS.md))을 우선 권장**합니다. 아래 로컬 방식은 클라우드를 쓸 수 없을 때의 대안입니다. 전체 검수 근거는 [AUDIT.md](AUDIT.md) 참조.

---

## 1. 무엇을 자동화하는가

| 알림 종류 | 시점 | 내용 |
|-----------|------|------|
| 신규 배분 알림 | 평일 09:00 ~ 18:00, 5분 주기 | 새로 배분된 티켓을 담당자 멘션과 함께 Slack 채널에 발송. 처리 완료된 티켓은 원본 메시지에 스레드로 완료 알림 |
| 아침 현황 요약 | 평일 09:00 | 전일 팀별 신규/완료 티켓 수 + 현재 잔여 `RECEIVED` 티켓 목록. 근무 시작 전 밀린 티켓 파악용 |

담당자별 스냅샷 비교로 신규 배분을 감지합니다. 첫 실행은 스냅샷만 초기화하고 알림을 발송하지 않으므로 **과거 누적 티켓 대량 발송 위험이 없습니다**.

---

## 2. 최종 아키텍처

```
Windows Task Scheduler
   ↓ (5분 주기 트리거)
wscript.exe run_notify.vbs        [UTF-16 BOM 저장, 창 숨김]
   ↓ WScript.Shell.Run(..., 0, True)
wsl.exe -d Ubuntu -- bash -lc
   ↓
python3 ticket_notifier.py notify
   ↓ HTTPS
플링커넥트 API + Slack API
```

핵심 결정 포인트:
- **Task Scheduler가 직접 wscript를 호출** — `.cmd` wrapper를 두면 한글 경로 인코딩(cmd cp949 ↔ bash UTF-8) 충돌로 실패.
- **VBS wrapper를 UTF-16 BOM으로 저장** — 한글 경로가 손실 없이 wsl로 전달되고, 콘솔 창이 뜨지 않음.
- **WSL Python 사용** — Windows Store stub Python 회피 + 원본 스크립트가 Linux `python3` 기준으로 작성됨.

---

## 3. 사전 요구사항

| 항목 | 값 |
|------|---|
| OS | Windows 10/11 |
| WSL 배포판 | Ubuntu 20.04 이상 (본 구성은 24.04 LTS) |
| WSL Python | 3.10 이상 (`/usr/bin/python3`) — pip 불필요 (스크립트는 stdlib만 사용) |
| Slack | Bot Token (`xoxb-…`), 대상 채널 ID, `chat:write` 스코프 |
| 플링커넥트 계정 | 이메일 + 비밀번호 (JWT 로그인용) |
| 관리자 권한 | 불필요 (사용자 세션 Task로 등록) |

---

## 4. 파일 구성

작업 디렉터리 예: `C:\Users\<사용자>\Documents\<팀>\VOC티켓전달\`

| 파일 | 역할 | 공유 여부 |
|------|------|-----------|
| `ticket_notifier.py` | 본체. `notify` / `summary` 두 모드. **시크릿 없음** | 공유 O (코드 자산) |
| `ticket_config.example.json` | 설정 템플릿(placeholder만) | 공유 O |
| `.gitignore` | 시크릿·상태·로그 커밋 차단 | 공유 O |
| `ticket_config.json` | **실제 자격증명·토큰**. example를 복사해 값 채움 | **공유 X** (.gitignore) |
| `ticket_state.json` | 담당자별 스냅샷 + 대기열 (자동 생성/갱신) | 공유 X (.gitignore) |
| `ticket_notifier.log` | 실행 로그 (자동 append) | 공유 X (.gitignore) |
| `run_notify.vbs` / `run_summary.vbs` | Task Scheduler → wsl 브릿지 | 공유 O (시크릿 없음) |

> **시크릿 분리 원칙**: 자격증명(플링커넥트 비밀번호·Slack 토큰)은 **소스코드에 절대 넣지 않는다.** `ticket_config.json`(gitignore 대상)에만 실제 값을 두고, 배포·공유할 때는 코드 + `ticket_config.example.json`만 넘긴다. 코드는 config 또는 환경변수(`PLUGLINK_EMAIL`/`PLUGLINK_PASSWORD`/`SLACK_BOT_TOKEN`)에서 런타임에 읽는다.

---

## 5. 설치 절차

### 5-1. `ticket_config.json` 작성 (시크릿은 여기에만)

`ticket_config.example.json`을 `ticket_config.json`으로 복사한 뒤 실제 값을 채웁니다. **소스코드는 건드리지 않습니다.**

```json
{
  "pluglink_email": "your-account@pluglink.kr",
  "pluglink_password": "YOUR_PLUGLINK_PASSWORD",
  "slack_bot_token": "xoxb-...",
  "slack_channel": "#your-voc-channel",
  "slack_channel_id": "C0XXXXXXXXX",
  "slack_member_ids": {
    "닉네임A": "U012ABCDEF",
    "닉네임B": "U013GHIJKL"
  }
}
```

- `pluglink_email` / `pluglink_password`: 플링커넥트 로그인 계정. **개인 계정 대신 최소권한 전용 서비스 계정 권장.** (환경변수 `PLUGLINK_EMAIL`/`PLUGLINK_PASSWORD`로 줘도 됨)
- `slack_channel_id`는 Slack 채널 세부정보 하단 채널 ID 복사. (채우면 넓은 스코프 조회를 피함)
- `slack_member_ids`의 멤버 ID는 Slack 프로필 > … > 멤버 ID 복사.
- 봇을 채널에 초대해 두어야 합니다.
- 이 파일은 `.gitignore`에 있어 커밋/공유되지 않습니다. **절대 이 파일을 그대로 전달하지 마세요.**

### 5-2. `ticket_notifier.py` 담당자 목록 조정

스크립트의 `TARGET_EMPLOYEES` 리스트와 **`send_daily_summary()` 함수 안의 `TEAMS` dict** 두 곳을 모두 자기 팀 닉네임으로 교체합니다. (자격증명은 5-1 config에서 관리하므로 소스 편집 대상이 아닙니다.)

> 주의: `TARGET_EMPLOYEES`(신규 알림 대상)와 `TEAMS`(아침 요약 대상)는 별개 위치입니다. 한쪽만 바꾸면 아침 요약이 어긋납니다. `slack_member_ids`의 키도 동일 닉네임이어야 합니다.

### 5-3. WSL Python 확인

PowerShell에서:

```powershell
wsl -- bash -c "python3 --version"
```

`Python 3.x.y`가 나오면 OK. pip은 필요 없음(스크립트는 `urllib` 등 stdlib만 사용).

### 5-4. VBS wrapper 생성 (UTF-16 BOM으로 저장이 중요)

PowerShell에서 다음을 실행하면 두 파일이 정확한 인코딩으로 만들어집니다. `<경로>`는 실제 폴더로 치환:

```powershell
$BASE = "<경로>"   # 예: C:\Users\user\Documents\claude\03_운영데이터\VOC-티켓전달
$WSL_PATH = "/mnt/c/Users/user/Documents/claude/03_운영데이터/VOC-티켓전달"  # 실제 팀 경로로

$notify = @"
Set sh = CreateObject("WScript.Shell")
sh.Run "C:\Windows\System32\wsl.exe -d Ubuntu -- bash -lc ""cd '$WSL_PATH' && python3 ticket_notifier.py notify >> ticket_notifier.log 2>&1""", 0, True
"@

$summary = @"
Set sh = CreateObject("WScript.Shell")
sh.Run "C:\Windows\System32\wsl.exe -d Ubuntu -- bash -lc ""cd '$WSL_PATH' && python3 ticket_notifier.py summary >> ticket_notifier.log 2>&1""", 0, True
"@

$utf16 = [System.Text.UnicodeEncoding]::new($false, $true)
[System.IO.File]::WriteAllBytes("$BASE\run_notify.vbs",  $utf16.GetPreamble() + $utf16.GetBytes($notify))
[System.IO.File]::WriteAllBytes("$BASE\run_summary.vbs", $utf16.GetPreamble() + $utf16.GetBytes($summary))
```

> **왜 UTF-16 BOM인가**: Windows Task Scheduler에서 실행되는 cmd는 시스템 기본 codepage(한글 Windows는 cp949)로 파일을 읽습니다. UTF-8로 저장된 `.cmd` 파일에 한글 경로가 있으면 파싱 실패로 exit 1. `.cmd`를 cp949로 바꾸어도 이번엔 wsl로 전달되는 한글이 깨집니다. VBS는 BOM이 있으면 wscript가 확실하게 UTF-16으로 해석하고, `WScript.Shell.Run` 인자는 Win32 API를 그대로 통과해 wsl에 손실 없이 전달됩니다.

### 5-5. Task Scheduler 등록 (관리자 권한 불필요)

```powershell
$BASE = "<경로>"
$notifyPath  = "$BASE\run_notify.vbs"
$summaryPath = "$BASE\run_summary.vbs"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
  -MultipleInstances IgnoreNew

# 신규 알림: 평일 09:00 ~ 18:00, 5분 주기
$actionN = New-ScheduledTaskAction -Execute "C:\Windows\System32\wscript.exe" `
  -Argument "`"$notifyPath`""
$trigN = New-ScheduledTaskTrigger -Weekly -At 9am `
  -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday
$trigN.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5) `
  -RepetitionDuration (New-TimeSpan -Hours 9)).Repetition
Register-ScheduledTask -TaskName "VOC_Notify" -Action $actionN `
  -Trigger $trigN -Settings $settings -Force

# 일일 요약: 평일 09:00
$actionS = New-ScheduledTaskAction -Execute "C:\Windows\System32\wscript.exe" `
  -Argument "`"$summaryPath`""
$trigS = New-ScheduledTaskTrigger -Weekly -At 9am `
  -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday
Register-ScheduledTask -TaskName "VOC_Summary" -Action $actionS `
  -Trigger $trigS -Settings $settings -Force
```

Task 이름은 팀 컨벤션에 맞춰 자유롭게 (`<팀명>_VOC_Notify` 등) 변경 가능합니다.

### 5-6. 첫 실행 검증

**먼저 dry-run으로 안전 검증** (Slack 미발송, 상태파일 미변경 — 매핑·포맷만 확인):

```powershell
wsl -- bash -lc "cd '/mnt/c/.../VOC티켓전달' && python3 ticket_notifier.py notify --dry-run"
wsl -- bash -lc "cd '/mnt/c/.../VOC티켓전달' && python3 ticket_notifier.py summary --dry-run"
```

`[DRY-RUN] slack chat.postMessage: ...`로 보낼 메시지가 출력되고 실제 발송/저장은 하지 않습니다. 담당자 멘션(`<@U…>`)이 평문 `@닉네임`으로 나오면 `slack_member_ids` 매핑 누락이니 config를 고치세요. 이상 없으면 아래 실제 트리거로 넘어갑니다.

```powershell
# 수동 트리거 (블로킹, 결과 표시)
Start-ScheduledTask -TaskName "VOC_Notify"
Start-Sleep 30

# 결과 확인
$info = Get-ScheduledTaskInfo "VOC_Notify"
"LastRun: $($info.LastRunTime)  LastResult: 0x{0:X}" -f $info.LastTaskResult

# 로그 확인
wsl -- bash -c "tail -20 '/mnt/c/.../VOC티켓전달/ticket_notifier.log'"
```

- `LastResult: 0x0` → 성공
- `LastResult: 0x1` → 스크립트 exit 1 (로그인 실패 등 로그 참조)
- `LastResult: 0x1` 이지만 로그에 아무것도 안 남음 → VBS 인코딩 재확인 (BOM 여부 hex로 검증)

첫 실행은 스냅샷 초기화만 하고 알림을 발송하지 않는 것이 정상입니다. 실제 신규 티켓이 들어와야 두 번째 실행부터 발송됩니다.

---

## 6. 알림 로직 요약

- **notify 모드**
  - 담당자별 페이지네이션으로 현재 티켓 조회 → 이전 스냅샷 대비 신규 ID 검출
  - 신규 티켓 중 `assignedAdminUserName` 있고 `status == RECEIVED`인 항목만 발송
  - **업무시간 외에 감지된 신규 티켓은 야간 대기열에 저장** → 다음 날 09:00 summary 실행 시 개별 발송 (RECEIVED 상태 유지 확인 후)
  - 발송 실패 티켓은 `retry_ids`에 등록, 다음 실행에서 재시도
  - 처리 완료(RECEIVED에서 다른 상태로 전이)된 티켓은 원본 알림에 스레드로 완료 코멘트 (Bot Token 필요)

- **summary 모드**
  - 야간 대기열 개별 발송 먼저 (전날 18시 이후 신규분)
  - 전일 팀별 신규 배분/완료 카운트 + 현재 잔여 RECEIVED 목록 발송

---

## 7. 커스터마이징 포인트

| 부분 | 위치 | 예시 |
|------|------|------|
| 업무시간 | `ticket_notifier.py` `is_business_hours()` | `9 <= hour < 18` → 자기 팀 기준으로 |
| 주기 | Task Scheduler `-RepetitionInterval` | 5분 → 10분 등 |
| 요일 | Task Scheduler `-DaysOfWeek` | 평일 → 매일 등 |
| 대상 채널 | `ticket_config.json` `slack_channel_id` | 팀 채널로 |
| 담당자 목록 | `ticket_notifier.py` `TARGET_EMPLOYEES` + `slack_member_ids` | 자기 팀 |
| 완료 상태 판정 | `ticket_notifier.py` `COMPLETED_STATUSES` | 팀 정책에 따라 |

---

## 8. 트러블슈팅

### 증상: Task는 트리거되는데 로그가 전혀 안 남음, LastResult 0x1

- 원인 후보 1: `.vbs` 파일이 UTF-8로 저장됨 → BOM 확인
  ```powershell
  Get-Content <path>.vbs -Encoding Byte -TotalCount 2 | ForEach-Object { $_.ToString('X2') }
  # 정상: FF FE (UTF-16 LE BOM)
  ```
- 원인 후보 2: WSL 배포판 이름이 `Ubuntu`가 아님 → `wsl -l -v`로 확인 후 vbs 안의 `-d Ubuntu` 부분 교체.

### 증상: 로그에 `cd: /mnt/c/…: No such file or directory` (경로 깨짐)

- 원인: `.cmd` wrapper를 경유하고 있음. `.cmd`는 인코딩 지뢰라 사용하지 말고 VBS로 직접 wsl 호출.

### 증상: 5분마다 검은 WSL 콘솔 창이 잠깐씩 뜸

- 원인: Task Action이 `wsl.exe`를 직접 호출 중. VBS wrapper 경유 방식으로 변경 (WScript.Shell.Run의 두 번째 인자 `0` = hidden).

### 증상: Slack 알림은 오는데 스레드 완료 코멘트가 안 달림

- 원인: Bot Token 미설정 또는 채널에 봇 미초대. `ticket_config.json`의 `slack_bot_token` 채우고 채널에 봇 초대.

### 증상: 첫 실행에서 갑자기 대량 알림 발송

- 원본 스크립트는 첫 실행 시 스냅샷만 초기화하고 알림을 보내지 않도록 설계됨. 대량 발송이 발생했다면 `ticket_state.json`이 이미 있고 내용이 손상됐거나 `TARGET_EMPLOYEES` 변경으로 인한 재초기화 지연. `ticket_state.json` 백업 후 삭제 → 재실행하면 다시 스냅샷만 초기화됩니다.

---

## 9. 운영 팁

- **PC 부팅 후 자동 재시작**: Task Scheduler에 등록해 두면 재부팅 후에도 자동으로 재개됩니다. WSL 데몬 별도 기동 불필요 (`wsl.exe`가 필요 시 배포판을 자동으로 시작).
- **PC 꺼져 있을 때**: Task는 실행되지 않지만 다음 부팅 시 `-StartWhenAvailable` 옵션으로 놓친 트리거 1회를 즉시 실행. 이후 정상 주기.
- **다른 PC로 이관**: `ticket_state.json`을 새 PC로 복사하면 스냅샷을 그대로 이어받아 중복 알림 없이 계속.
- **로그 로테이션**: `ticket_notifier.log`가 커지면 수동으로 archive. 스크립트는 append만 하므로 삭제해도 다음 실행이 새로 만듭니다.

---

## 10. 보안·주의

**시크릿 취급 (필수 체크리스트)**

- [ ] 소스코드(`ticket_notifier.py`)에는 시크릿이 없습니다. 자격증명은 `ticket_config.json`(또는 환경변수)에서만 로드됩니다.
- [ ] `ticket_config.json` / `ticket_state.json` / `*.log`는 `.gitignore`에 등록되어 있습니다. **이 파일들을 그대로 복사·공유·업로드하지 마세요.**
- [ ] 배포·공유 시에는 **코드 + `ticket_config.example.json` + `.gitignore`만** 넘깁니다. 받는 팀은 example를 복사해 자기 값을 채웁니다.
- [ ] 자격증명이 이미 외부(이전 소스/로그/공유본)에 노출된 적이 있다면 **즉시 회전**하세요: 플링커넥트 비밀번호 변경, Slack 앱 관리에서 Bot Token revoke/재발급 → 새 값을 `ticket_config.json`에 반영.
- [ ] 가능하면 개인 계정 대신 **최소권한 전용 서비스 계정**을 사용하세요(개인 비밀번호 회전 시 자동화가 멈추는 것을 방지).

**단일 장애점 주의**

- 이 로컬 방식은 소유자 PC가 켜져 있어야만 동작하는 단일 장애점입니다. 팀 SLA가 걸린 알림이면 조직 상시가동 인프라(n8n / GitHub Actions cron)로 이전을 권장합니다. 상세는 별도 검수 보고서(`AUDIT.md`) 참조.
