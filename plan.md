# 작업지시서: VOC 티켓 알림 — Claude Code 스케줄 설정

## 목적

매일 진행 중인 두 가지 VOC 알림 작업을 Claude Code의 `/schedule` 기능으로 동일하게 동작시킨다.

| 알림 | 시점 | 기능 |
|------|------|------|
| 신규 티켓 배분 알림 | 평일 9~18시, 5분마다 | 새로 배분된 티켓 Slack 알림 + 처리 완료 스레드 |
| 아침 현황 요약 | 평일 09:00 KST | 전일 팀별 신규/완료 티켓 및 현재 잔여 현황 |

---

## 사전 확인 (이미 완료)

- **스크립트**: `ticket_notifier.py` — 워크스페이스에 존재
- **Slack 설정**: `ticket_config.json` — Bot Token, Channel ID, 멤버 ID 모두 설정 완료
  - 채널: `#s3-사업개발-voc-tickets`
  - 팀원: 엔젤, 마크, 우성, 쿠이, 엘리, 케이시, 윤택, 체셔
- **실행 명령**:
  - 신규 알림: `python3 ticket_notifier.py notify`
  - 아침 요약: `python3 ticket_notifier.py summary`

---

## Claude Code에서 설정하는 방법

### Step 1. 신규 티켓 알림 스케줄 생성

Claude Code 채팅창에 다음 메시지를 입력합니다:

```
/schedule
평일(월~금) 오전 9시~오후 6시 사이, 5분마다 VOC 신규 티켓을 확인하고 Slack으로 알림을 보내주세요.
실행할 명령:
cd /home/kwj7348/.paperclip/instances/default/workspaces/40773e92-355f-44bf-9610-7735fc04a747 && python3 ticket_notifier.py notify

cron 표현식: */5 9-18 * * 1-5 (시간대: Asia/Seoul)
```

→ `/schedule` 스킬이 Paperclip 루틴을 생성하고 평일 업무시간마다 자동 실행됩니다.

---

### Step 2. 아침 현황 요약 스케줄 생성

Claude Code 채팅창에 다음 메시지를 입력합니다:

```
/schedule
매일(평일) 오전 9시에 VOC 티켓 일일 현황 요약을 Slack으로 보내주세요.
실행할 명령:
cd /home/kwj7348/.paperclip/instances/default/workspaces/40773e92-355f-44bf-9610-7735fc04a747 && python3 ticket_notifier.py summary

cron 표현식: 0 9 * * 1-5 (시간대: Asia/Seoul)
```

→ 매 평일 오전 9시에 자동으로 전일 팀별 신규/완료 통계와 현재 잔여 현황이 Slack으로 발송됩니다.

---

### Step 3. 수동 테스트

설정 후 즉시 동작 확인:

```bash
# 신규 알림 테스트
cd /home/kwj7348/.paperclip/instances/default/workspaces/40773e92-355f-44bf-9610-7735fc04a747
python3 ticket_notifier.py notify

# 아침 요약 테스트
cd /home/kwj7348/.paperclip/instances/default/workspaces/40773e92-355f-44bf-9610-7735fc04a747
python3 ticket_notifier.py summary
```

Slack `#s3-사업개발-voc-tickets` 채널에서 메시지 수신 확인.

---

### Step 4. 스케줄 목록 확인

설정된 스케줄 목록은 Claude Code에서 다음으로 확인:

```
/schedule list
```

---

## 참고: 스크립트 실행 모드 설명

| 명령 | 동작 |
|------|------|
| `ticket_notifier.py notify` | 스냅샷 방식으로 신규 배분 티켓 감지, RECEIVED 상태인 경우 Slack 알림 발송. 처리 완료 티켓은 원본 메시지에 스레드로 완료 알림 |
| `ticket_notifier.py summary` | 전일 팀별 신규 배분/완료 티켓 목록 + 현재 잔여(RECEIVED) 티켓 현황 발송. 업무 전 잔여 티켓 파악용 |

---

## 완료 조건

- [ ] 신규 티켓 알림 스케줄 생성 완료
- [ ] 아침 현황 요약 스케줄 생성 완료
- [ ] 수동 테스트 시 Slack 알림 수신 확인
- [ ] 5분 후 자동 실행 확인
