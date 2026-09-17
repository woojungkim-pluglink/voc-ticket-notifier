#!/usr/bin/env python3
"""
플러그링크커넥트 티켓 Slack 알림 스크립트
- 5분마다 실행 (cron): 신규 배분 티켓 알림 + 처리 완료 스레드 알림
- 매일 09:00 실행 (summary mode): 잔여 신규접수 현황 요약
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

# E4: --dry-run — Slack 발송·상태 저장을 하지 않고 무엇을 보낼지 출력만 한다(매핑·포맷 안전 검증용).
DRY_RUN = "--dry-run" in sys.argv

# ──────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────

API_BASE = "https://apis.pluglink.kr/v101"
CONNECT_BASE = "https://connect.pluglink.kr"

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_config = load_config()

# 플링커넥트 자격증명은 소스에 두지 않는다 — ticket_config.json(gitignore 대상) 또는 환경변수에서 로드.
# 소스코드에 평문 하드코딩 금지. config 미설정 시 환경변수 PLUGLINK_EMAIL / PLUGLINK_PASSWORD 폴백.
PLUGLINK_EMAIL = _config.get("pluglink_email") or os.environ.get("PLUGLINK_EMAIL", "")
PLUGLINK_PASSWORD = _config.get("pluglink_password") or os.environ.get("PLUGLINK_PASSWORD", "")

SLACK_WEBHOOK_URL = _config.get("slack_webhook_url") or os.environ.get("SLACK_WEBHOOK_URL", "")
SLACK_BOT_TOKEN = _config.get("slack_bot_token") or os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL = _config.get("slack_channel", "#사업개발-voc관리")
SLACK_CHANNEL_ID = _config.get("slack_channel_id", "")

# 닉네임 → Slack 멤버 ID 매핑 (ticket_config.json에서 로드)
SLACK_MEMBER_IDS = _config.get("slack_member_ids", {})

# 알림 대상 직원 닉네임
TARGET_EMPLOYEES = [
    "엔젤",   # 정해성(엔젤) - 영업관리팀
    "마크",   # 신동진(마크) - 영업관리팀
    "우성",   # 장순재(우성) - 영업관리팀
    "쿠이",   # 김우중(쿠이) - 시공관리팀
    "엘리",   # 허은실(엘리) - 시공관리팀
    "케이시", # 김충근(케이시) - 시공관리팀
    "윤택",   # 김택윤(윤택) - 시공관리팀
    "체셔",   # 양대열(체셔) - 시공관리팀
]

# 완료(종결)로 간주하는 상태. 중간 상태(PROCESSING/MONITORING)는 여기에 없어야 완료 오판을 막는다.
# (API 실측 종결 상태: COMPLETED, CANCELLED. 그 외 값은 방어적으로 포함)
COMPLETED_STATUSES = {"COMPLETED", "CLOSED", "DONE", "CANCELED", "CANCELLED", "FINISH", "FINISHED"}

# 일일 요약에서 '처리 완료'로 집계·조회할 상태 목록 (API가 실제 반환하는 종결 상태).
# get_daily_delta가 상태별로 조회해 합산하므로, 너무 넓히면 불필요한 API 호출이 늘어난다.
SUMMARY_DONE_STATUSES = ["COMPLETED", "CANCELLED"]

# 상태 파일
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticket_state.json")
INITIAL_LOOKBACK_HOURS = 24

# ──────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────

def get_slack_mention(assignee_full_name):
    """담당자 전체 이름에서 닉네임 추출 후 Slack 멘션 문자열 반환"""
    for nickname, member_id in SLACK_MEMBER_IDS.items():
        if nickname in (assignee_full_name or ""):
            if member_id:
                return f"<@{member_id}>"
            else:
                return f"@{nickname}"
    return assignee_full_name or "-"

def load_state():
    default = {"notified_ids": [], "last_check": None, "ticket_ts_map": {}, "completed_ids": []}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            # C2: 손상된 state는 .corrupt로 백업 후 빈 상태로 안전 재시작(무한 크래시 루프 방지).
            # 첫 실행처럼 스냅샷만 초기화되므로 대량발송은 발생하지 않는다.
            print(f"[WARN] ticket_state.json 손상/읽기 실패({e}) — .corrupt 백업 후 초기화")
            try:
                os.replace(STATE_FILE, STATE_FILE + ".corrupt")
            except Exception:
                pass
            return default
    return default

def save_state(state):
    if DRY_RUN:
        print("  [DRY-RUN] save_state 스킵 (상태 미변경)")
        return
    state["notified_ids"] = state["notified_ids"][-1000:]
    state["last_check"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    # ticket_ts_map: 최근 500개만 유지
    if len(state.get("ticket_ts_map", {})) > 500:
        items = list(state["ticket_ts_map"].items())
        state["ticket_ts_map"] = dict(items[-500:])
    # C2: 원자적 쓰기 — 임시파일에 쓴 뒤 os.replace로 교체(쓰기 도중 중단돼도 원본 보존).
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)

# ──────────────────────────────────────────────
# PlugLinkConnect API
# ──────────────────────────────────────────────

COMMON_HEADERS = {
    "x-channel": "PLUGLINK",
    "x-platform": "WEB",
    "x-token": "PLUGLINK",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; PluglinkVOCBot/1.0)",
    "Origin": "https://connect.pluglink.kr",
}

def api_request(url, method="GET", data=None, headers=None):
    req_headers = dict(COMMON_HEADERS)
    if headers:
        req_headers.update(headers)
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"HTTP {e.code}: {body[:200]}")

def login():
    url = f"{API_BASE}/auths/admins/signIn"
    headers = {"x-token": "1", "x-channel": "PLUGLINK", "x-platform": "WEB",
               "Content-Type": "application/json",
               "Origin": "https://connect.pluglink.kr",
               "User-Agent": "Mozilla/5.0"}
    data = {"email": PLUGLINK_EMAIL, "password": PLUGLINK_PASSWORD,
            "authType": "ORGANIC", "partnerId": 1}
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["data"]["jwtToken"]

def get_tickets(jwt_token, employee_nickname, page=1, size=50, status=None):
    params = {"page": page, "size": size, "assignedAdminUserName": employee_nickname}
    if status:
        params["status"] = status
    url = f"{API_BASE}/crms/tickets?{urllib.parse.urlencode(params)}"
    result = api_request(url, headers={"Authorization": f"Bearer {jwt_token}"})
    return result.get("data", {})

def get_ticket_by_id(jwt_token, ticket_id):
    """개별 티켓 정보 조회"""
    url = f"{API_BASE}/crms/tickets/{ticket_id}"
    try:
        result = api_request(url, headers={"Authorization": f"Bearer {jwt_token}"})
        return result.get("data")
    except Exception:
        return None

# ──────────────────────────────────────────────
# Slack API (Bot Token 기반 — 스레드 지원)
# ──────────────────────────────────────────────

def slack_api_call(method, payload):
    """Slack Web API 호출 (Bot Token 필요)"""
    if DRY_RUN:
        preview = json.dumps(payload, ensure_ascii=False)
        # 공개 로그 보호: 리포가 public 이면 Actions 로그가 전부 공개된다.
        # 본문에는 채널 ID·담당자 member ID·처리시각이 들어가므로 기본은 미출력.
        # 로컬 디버깅에서 본문을 보려면 VOC_LOG_BODY=1 로 실행한다.
        if os.environ.get("VOC_LOG_BODY") == "1":
            print(f"  [DRY-RUN] slack {method}: {preview[:400]}")
        else:
            print(f"  [DRY-RUN] slack {method} — 본문 미출력(VOC_LOG_BODY=1 로 확인)")
        return {"ok": True, "ts": "DRYRUN"}
    url = f"https://slack.com/api/{method}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except Exception as e:
        print(f"  [ERROR] Slack API 호출 실패 ({method}): {e}")
        return {"ok": False, "error": str(e)}

def get_channel_id():
    """채널 ID 조회 및 캐싱"""
    global SLACK_CHANNEL_ID
    if SLACK_CHANNEL_ID:
        return SLACK_CHANNEL_ID

    channel_name = SLACK_CHANNEL.lstrip("#")
    cursor = None
    while True:
        params = {"limit": 200, "exclude_archived": "true", "types": "public_channel,private_channel"}
        if cursor:
            params["cursor"] = cursor
        result = slack_api_call("conversations.list", params)
        if not result.get("ok"):
            print(f"  [WARN] 채널 목록 조회 실패: {result.get('error')}")
            return None
        for ch in result.get("channels", []):
            if ch.get("name") == channel_name:
                SLACK_CHANNEL_ID = ch["id"]
                # 설정 파일에 저장
                try:
                    cfg = load_config()
                    cfg["slack_channel_id"] = SLACK_CHANNEL_ID
                    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                        json.dump(cfg, f, ensure_ascii=False, indent=2)
                    print(f"  채널 ID 저장: {SLACK_CHANNEL_ID}")
                except Exception:
                    pass
                return SLACK_CHANNEL_ID
        next_cursor = result.get("response_metadata", {}).get("next_cursor")
        if not next_cursor:
            break
        cursor = next_cursor

    # 채널을 못 찾으면 채널 이름 직접 사용 (일부 API는 이름도 허용)
    return SLACK_CHANNEL

def send_message_with_bot(blocks, thread_ts=None):
    """Bot Token으로 메시지 전송. 성공 시 ts 반환, 실패 시 None 반환."""
    channel = get_channel_id() or SLACK_CHANNEL
    payload = {"channel": channel, "blocks": blocks}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    result = slack_api_call("chat.postMessage", payload)
    if result.get("ok"):
        return result.get("ts")
    else:
        print(f"  [ERROR] Bot 메시지 전송 실패: {result.get('error')}")
        return None

def send_message_with_webhook(payload):
    """Incoming Webhook으로 메시지 전송 (ts 반환 불가)"""
    if DRY_RUN:
        if os.environ.get("VOC_LOG_BODY") == "1":
            print(f"  [DRY-RUN] webhook: {json.dumps(payload, ensure_ascii=False)[:400]}")
        else:
            print("  [DRY-RUN] webhook — 본문 미출력(VOC_LOG_BODY=1 로 확인)")
        return True
    if not SLACK_WEBHOOK_URL:
        return False
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(SLACK_WEBHOOK_URL, data=body,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8") == "ok"
    except Exception as e:
        print(f"  [ERROR] Webhook 발송 실패: {e}")
        return False

# ──────────────────────────────────────────────
# Slack 알림 — 개별 티켓
# ──────────────────────────────────────────────

def format_ticket_blocks(ticket):
    ticket_id = ticket.get("id", "?")
    created_at = ticket.get("createdAt", "-")
    assignee_full = ticket.get("assignedAdminUserName", "-")
    station = ticket.get("targetStationName") or "-"
    address = ticket.get("targetStationAddress") or "-"
    content = ticket.get("requestContent") or "-"

    mention = get_slack_mention(assignee_full)

    summary_lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
    summary = " / ".join(summary_lines[:3])
    if len(summary) > 150:
        summary = summary[:147] + "..."

    parent_voc_id = ticket.get("parentVocId")
    if parent_voc_id:
        ticket_link = f"{CONNECT_BASE}/operation/vocs/manage/{parent_voc_id}?ticketId={ticket_id}"
    else:
        ticket_link = f"{CONNECT_BASE}/operation/tickets/manage"

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"🎫 새 티켓 배분 알림 (#{ticket_id})", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*🕐 생성시각*\n{created_at}"},
                {"type": "mrkdwn", "text": f"*👤 담당자*\n{mention}"},
                {"type": "mrkdwn", "text": f"*⚡ 충전소*\n{station}"},
                {"type": "mrkdwn", "text": f"*📍 주소*\n{address}"},
            ]
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*📝 요약*\n{summary}"}
        },
        {
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "티켓 확인하기"},
                 "url": ticket_link, "style": "primary"}
            ]
        },
        {"type": "divider"}
    ]

def send_slack_notification(ticket):
    """신규 티켓 알림 발송. Bot Token이 있으면 ts 반환, 없으면 True/False 반환."""
    blocks = format_ticket_blocks(ticket)

    if SLACK_BOT_TOKEN:
        ts = send_message_with_bot(blocks)
        if ts:
            print(f"     Slack Bot 발송 완료 (ts={ts})")
            return ts
        print(f"     Bot 발송 실패 — Webhook으로 재시도")

    # Webhook 폴백
    if send_message_with_webhook({"blocks": blocks}):
        print(f"     Slack Webhook 발송 완료 (스레드 추적 불가)")
        return True
    return False

# ──────────────────────────────────────────────
# 처리 완료 스레드 알림
# ──────────────────────────────────────────────

def format_completion_text(ticket):
    """처리 완료 스레드 메시지 포맷"""
    ticket_id = ticket.get("id", "?")
    status = ticket.get("status", "")
    assignee_full = ticket.get("assignedAdminUserName", "-")
    completed_at = ticket.get("updatedAt") or ticket.get("completedAt") or "-"

    status_label = {
        "COMPLETED": "처리 완료",
        "CLOSED": "종료",
        "DONE": "완료",
        "CANCELED": "취소",
        "CANCELLED": "취소",
        "FINISH": "완료",
        "FINISHED": "완료",
    }.get(status, f"상태 변경: {status}")

    mention = get_slack_mention(assignee_full)

    return f"✅ *티켓 #{ticket_id} {status_label}*\n👤 담당자: {mention}\n🕐 처리시각: {completed_at}"

def check_and_notify_completions(jwt_token, state):
    """알림을 보낸 티켓 중 완료된 것에 스레드 댓글 발송"""
    if not SLACK_BOT_TOKEN:
        print("[SKIP] Bot Token 미설정 — 완료 스레드 알림 불가")
        return

    ticket_ts_map = state.get("ticket_ts_map", {})
    completed_ids = set(state.get("completed_ids", []))

    if not ticket_ts_map:
        return

    # 완료 처리가 안 된 티켓만 확인 (완료 처리된 것 제외)
    pending_ids = [tid for tid in ticket_ts_map if str(tid) not in completed_ids and tid not in completed_ids]

    if not pending_ids:
        return

    print(f"완료 여부 확인 중: {len(pending_ids)}건...")
    channel = get_channel_id() or SLACK_CHANNEL
    newly_completed = 0

    for ticket_id in pending_ids:
        ts = ticket_ts_map.get(ticket_id) or ticket_ts_map.get(str(ticket_id))
        if not ts or not isinstance(ts, str):
            # ts가 없거나 webhook으로 보낸 경우 스킵
            continue

        try:
            ticket = get_ticket_by_id(jwt_token, ticket_id)
            if not ticket:
                continue

            ticket_status = ticket.get("status", "")
            # 중간 상태(PROCESSING/MONITORING 등)는 완료가 아니므로 계속 추적만 하고 알림하지 않는다.
            # 완료 판정은 COMPLETED_STATUSES 화이트리스트로만. (과거 catch-all이 중간상태를 완료로 오판)
            if ticket_status not in COMPLETED_STATUSES:
                continue  # RECEIVED 또는 중간 상태 — 다음 실행에서 재확인

            print(f"  -> 티켓 #{ticket_id} 완료 감지 (status={ticket_status})")
            text = format_completion_text(ticket)
            result = slack_api_call("chat.postMessage", {
                "channel": channel,
                "thread_ts": ts,
                "text": text,
            })
            if result.get("ok"):
                print(f"     스레드 댓글 발송 완료")
                completed_ids.add(str(ticket_id))
                newly_completed += 1
            else:
                err = result.get("error")
                print(f"     스레드 발송 실패: {err}")
                # C6: 설정성 오류(채널 미초대 등)는 재시도해도 무의미 — completed 처리해 무한 재조회 방지
                if err in ("not_in_channel", "channel_not_found", "is_archived"):
                    print(f"     [WARN] 봇이 채널에 없음/아카이브 — 재시도 중단 위해 완료 처리. 봇 채널 초대 필요.")
                    completed_ids.add(str(ticket_id))
        except Exception as e:
            print(f"  [{ticket_id}] 완료 확인 오류: {e}")

    state["completed_ids"] = list(completed_ids)[-1000:]
    print(f"완료 처리: {newly_completed}건 스레드 발송")

# ──────────────────────────────────────────────
# 전일 영업일 델타 집계
# ──────────────────────────────────────────────

def get_previous_business_day(today=None):
    """전 영업일(월요일이면 금요일) 날짜 반환"""
    if today is None:
        today = datetime.now(timezone(timedelta(hours=9))).date()
    day = today - timedelta(days=1)
    while day.weekday() >= 5:  # 토=5, 일=6
        day -= timedelta(days=1)
    return day

def get_tickets_paged(jwt_token, nickname, status=None, max_pages=20):
    """전체 페이지 티켓 조회 (size=100)"""
    all_tickets = []
    for page in range(1, max_pages + 1):
        try:
            data = get_tickets(jwt_token, nickname, page=page, size=100, status=status)
            content = data.get("content", [])
            all_tickets.extend(content)
            total_pages = data.get("totalPages", 1)
            if page >= total_pages:
                break
        except Exception as e:
            print(f"  [{nickname}] 페이지 {page} 오류: {e}")
            break
    return all_tickets

def get_daily_delta(jwt_token, target_date):
    """대상 날짜의 담당자별 신규 배분 티켓 목록 및 처리 완료 티켓 목록 반환"""
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"전일 델타 집계 중 ({date_str})...")
    results = {}

    for nickname in TARGET_EMPLOYEES:
        # 신규 배분: createdAt = target_date 인 티켓 목록
        new_tickets = []
        for page in range(1, 30):
            try:
                data = get_tickets(jwt_token, nickname, page=page, size=100)
                content = data.get("content", [])
                stop = False
                for t in content:
                    ca = t.get("createdAt", "")
                    if ca.startswith(date_str):
                        new_tickets.append(t)
                    elif ca < date_str:
                        stop = True
                        break
                total_pages = data.get("totalPages", 1)
                if stop or page >= total_pages:
                    break
            except Exception as e:
                print(f"  [{nickname}] 신규 집계 오류: {e}")
                break

        # 처리 완료: 대상일에 종료된 티켓 목록.
        # 완료 상태는 COMPLETED 외 CANCELLED 등도 있으므로 완료성 상태를 모두 조회하고,
        # 완료일자는 completedAt이 비는 경우가 많아 updatedAt으로 폴백해 대상일과 비교한다.
        completed_tickets = []
        seen_done = set()
        for done_status in SUMMARY_DONE_STATUSES:
            try:
                tickets = get_tickets_paged(jwt_token, nickname, status=done_status, max_pages=15)
                for t in tickets:
                    done_date = (t.get("completedAt") or t.get("updatedAt") or "")
                    tid = t.get("id")
                    if done_date.startswith(date_str) and tid not in seen_done:
                        completed_tickets.append(t)
                        seen_done.add(tid)
            except Exception as e:
                print(f"  [{nickname}] 완료 집계 오류({done_status}): {e}")

        results[nickname] = {"new": new_tickets, "completed": completed_tickets}
        print(f"  [{nickname}] 신규={len(new_tickets)}건, 완료={len(completed_tickets)}건")

    return results

# ──────────────────────────────────────────────
# Slack 알림 — 일일 현황 요약
# ──────────────────────────────────────────────

def _ticket_summary_line(ticket):
    """티켓 한 줄 요약: #ID 충전소명 (요청내용 앞부분)"""
    tid = ticket.get("id", "?")
    station = ticket.get("targetStationName") or "-"
    content = ticket.get("requestContent") or ""
    # 첫 줄 또는 최대 40자
    first_line = content.strip().splitlines()[0].strip() if content.strip() else "-"
    if len(first_line) > 40:
        first_line = first_line[:38] + "…"
    parent_voc_id = ticket.get("parentVocId")
    if parent_voc_id:
        link = f"{CONNECT_BASE}/operation/vocs/manage/{parent_voc_id}?ticketId={tid}"
        return f"• <{link}|#{tid}> {station} — {first_line}"
    return f"• #{tid} {station} — {first_line}"


def get_remaining_tickets_by_team(jwt_token, teams):
    """팀별 현재 잔여 티켓(RECEIVED 상태) 수 및 목록 반환"""
    result = {}
    for team, members in teams.items():
        team_tickets = []
        for nickname in members:
            try:
                tickets = get_tickets_paged(jwt_token, nickname, status="RECEIVED", max_pages=20)
                team_tickets.extend(tickets)
            except Exception as e:
                print(f"  [{nickname}] 잔여 티켓 조회 오류: {e}")
        result[team] = team_tickets
        print(f"  [{team}] 잔여 티켓 {len(team_tickets)}건")
    return result


def send_daily_summary(jwt_token):
    """매일 9시: 현재 잔여 티켓 현황 + 전일 팀별 신규 배분/완료 티켓 목록 발송"""
    print("일일 현황 요약 집계 중...")
    kst_now = datetime.now(timezone(timedelta(hours=9)))
    today = kst_now.strftime("%Y년 %m월 %d일")
    prev_day = get_previous_business_day(kst_now.date())
    prev_day_str = prev_day.strftime("%Y년 %m월 %d일")

    TEAMS = {
        "영업관리팀": ["엔젤", "마크", "우성"],
        "시공관리팀": ["쿠이", "엘리", "케이시", "윤택", "체셔"],
    }

    # 현재 잔여 티켓 현황
    print("잔여 티켓 집계 중...")
    remaining = get_remaining_tickets_by_team(jwt_token, TEAMS)

    # 전일 신규 배분 / 완료 티켓 목록
    delta = get_daily_delta(jwt_token, prev_day)

    total_remaining = sum(len(v) for v in remaining.values())

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 VOC 티켓 일일 현황 — {today}", "emoji": True}
        },
        {"type": "divider"},
    ]

    # ── 섹션 1: 현재 잔여 티켓 현황 ──
    remaining_lines = [f"📌 *현재 잔여 티켓 현황* (미처리 RECEIVED)  |  전체 *{total_remaining}건*"]
    for team, tickets in remaining.items():
        member_counts = {}
        for t in tickets:
            name = t.get("assignedAdminUserName", "?")
            member_counts[name] = member_counts.get(name, 0) + 1
        member_str = "  ".join(
            f"{get_slack_mention(name)} {cnt}건"
            for name, cnt in sorted(member_counts.items())
        )
        remaining_lines.append(f"  *{team}* {len(tickets)}건  —  {member_str if member_str else '없음'}")

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(remaining_lines)}
    })
    blocks.append({"type": "divider"})

    # ── 섹션 2: 전일 변화 현황 ──
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"📅 전일 변화 기준일: *{prev_day_str}*"}]
    })

    grand_new = 0
    grand_done = 0

    for team, members in TEAMS.items():
        team_new_tickets = []
        team_done_tickets = []
        for nickname in members:
            team_new_tickets.extend(delta.get(nickname, {}).get("new", []))
            team_done_tickets.extend(delta.get(nickname, {}).get("completed", []))

        grand_new += len(team_new_tickets)
        grand_done += len(team_done_tickets)

        lines = [f"📊 *{team}*  _신규 배분 +{len(team_new_tickets)}건 / 처리 완료 {len(team_done_tickets)}건_"]

        if team_new_tickets:
            lines.append(f"\n🆕 *신규 배분*")
            for t in team_new_tickets:
                assignee = t.get("assignedAdminUserName", "")
                mention = get_slack_mention(assignee)
                lines.append(f"  {_ticket_summary_line(t)}  _{mention}_")

        if team_done_tickets:
            lines.append(f"\n✅ *처리 완료*")
            for t in team_done_tickets:
                assignee = t.get("assignedAdminUserName", "")
                mention = get_slack_mention(assignee)
                lines.append(f"  {_ticket_summary_line(t)}  _{mention}_")

        if not team_new_tickets and not team_done_tickets:
            lines.append("\n변화 없음")

        text = "\n".join(lines)
        if len(text) > 2900:
            text = text[:2897] + "…"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        })
        blocks.append({"type": "divider"})

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"🔢 전일 전체: 신규 배분 *+{grand_new}건* / 처리 완료 *{grand_done}건* | 매일 오전 9시 자동 발송"}
        ]
    })

    if SLACK_BOT_TOKEN:
        ts = send_message_with_bot(blocks)
        if ts:
            print(f"일일 요약 발송 완료 (bot, ts={ts})")
            return
    if send_message_with_webhook({"blocks": blocks}):
        print("일일 요약 발송 완료 (webhook)")
    else:
        print("[ERROR] 일일 요약 발송 실패")

# ──────────────────────────────────────────────
# 신규 티켓 감지 (스냅샷 기반)
# ──────────────────────────────────────────────

def find_new_tickets(jwt_token, state):
    """
    스냅샷 비교 방식으로 신규 배분 티켓 감지 + 발송 실패 티켓 재시도.
    - 첫 실행: 현재 상태를 스냅샷으로 저장하고 알림 없음
    - 이후 실행: 스냅샷에 없는 새 ID + retry_ids에 있는 ID를 알림 대상으로 포함
    """
    employee_snapshot = state.setdefault("employee_snapshot", {})
    notified_ids = set(str(tid) for tid in state.get("notified_ids", []))
    retry_ids = set(str(tid) for tid in state.get("retry_ids", []))
    new_tickets = []
    seen_tids = set()

    for nickname in TARGET_EMPLOYEES:
        print(f"  [{nickname}] 티켓 조회 중...")
        current_map = {}  # str(id) -> ticket
        try:
            for page in range(1, 20):
                data = get_tickets(jwt_token, nickname, page=page, size=100)
                content = data.get("content", [])
                for t in content:
                    tid = str(t.get("id"))
                    current_map[tid] = t
                if page >= data.get("totalPages", 1):
                    break
        except Exception as e:
            print(f"  [{nickname}] 조회 오류: {e}")
            continue

        initialized = nickname in employee_snapshot
        prev_ids = set(str(x) for x in employee_snapshot.get(nickname, []))

        # C3: 이미 초기화된 담당자인데 이번 조회가 0건이면 비정상(빈/오류 응답) 가능성이 높다.
        # 티켓은 삭제되지 않으므로 '있다가 0건'은 정상 상황이 아님 → 스냅샷을 덮어쓰지 않고 스킵해
        # 그 사이 배분된 티켓이 알림 없이 흡수되는 것을 막는다.
        if initialized and not current_map:
            print(f"  [{nickname}] 조회 0건(이전 {len(prev_ids)}건) — 비정상 응답 가능성, 스냅샷 유지·스킵")
            continue

        # D3: '초기화 여부'를 빈 리스트가 아니라 키 존재로 판정한다.
        # (티켓 0건 담당자도 한 번 초기화되면 이후 첫 티켓을 신규로 감지 — 흡수하지 않음)
        if not initialized:
            employee_snapshot[nickname] = list(current_map.keys())
            print(f"  [{nickname}] 스냅샷 초기화 ({len(current_map)}건)")
        else:
            newly_assigned = set(current_map.keys()) - prev_ids - notified_ids
            for tid in newly_assigned:
                t = current_map[tid]
                if t.get("assignedAdminUserName") and t.get("status") == "RECEIVED" and tid not in seen_tids:
                    new_tickets.append(t)
                    seen_tids.add(tid)
            employee_snapshot[nickname] = list(current_map.keys())
            if newly_assigned:
                print(f"  [{nickname}] 신규 배분 감지 {len(newly_assigned)}건 (RECEIVED 필터 적용)")

        # 발송 실패 티켓 재시도 (retry_ids)
        retry_for_employee = retry_ids & set(current_map.keys())
        for tid in retry_for_employee:
            if tid in seen_tids:
                continue
            t = current_map[tid]
            if t.get("assignedAdminUserName") and t.get("status") == "RECEIVED":
                new_tickets.append(t)
                seen_tids.add(tid)
                print(f"  [{nickname}] 재시도 대상: 티켓 #{tid}")

    return new_tickets

# ──────────────────────────────────────────────
# 업무시간 체크
# ──────────────────────────────────────────────

def is_business_hours():
    """현재 KST 시간이 업무시간(9시~18시)인지 확인"""
    kst_hour = datetime.now(timezone(timedelta(hours=9))).hour
    return 9 <= kst_hour < 18

# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main():
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = positional[0] if positional else "notify"
    dry = " [DRY-RUN]" if DRY_RUN else ""
    print(f"=== 플러그링크 티켓 알림 [{mode}]{dry} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")

    if not PLUGLINK_EMAIL or not PLUGLINK_PASSWORD:
        print("[ERROR] 플링커넥트 자격증명이 설정되지 않았습니다. "
              "ticket_config.json의 pluglink_email/pluglink_password 또는 "
              "환경변수 PLUGLINK_EMAIL/PLUGLINK_PASSWORD를 설정하세요.")
        sys.exit(1)

    try:
        jwt_token = login()
        print("로그인 성공")
    except Exception as e:
        print(f"로그인 실패: {e}")
        sys.exit(1)

    if mode == "summary":
        state = load_state()

        # 야간 대기열 티켓 먼저 개별 발송 (전날 18시 이후 지정된 티켓)
        overnight_queue = state.pop("overnight_queue", [])
        if overnight_queue:
            print(f"야간 대기열 {len(overnight_queue)}건 개별 발송...")
            ticket_ts_map = state.setdefault("ticket_ts_map", {})
            # C4: 발송에 실패했거나 조회가 안 된 티켓은 큐에 남겨 다음 실행에서 재시도.
            # (과거엔 pop 후 실패분을 버려 야간 티켓이 영구 유실됐음)
            still_pending = []
            for tid in overnight_queue:
                ticket = get_ticket_by_id(jwt_token, tid)
                if not ticket:
                    still_pending.append(tid)  # 조회 실패 → 재시도 위해 큐 유지
                    print(f"  -> 티켓 #{tid} 조회 실패 — 대기열 유지")
                    continue
                # 아직 RECEIVED 상태인 경우만 발송 (이미 처리됐으면 발송 불필요 → 큐에서 제거)
                if ticket.get("status") != "RECEIVED":
                    print(f"  -> 티켓 #{tid} 이미 처리됨 ({ticket.get('status')}) — 스킵")
                    continue
                assignee = ticket.get("assignedAdminUserName", "?")
                print(f"  -> 야간 대기 티켓 #{tid}")
                result = send_slack_notification(ticket)
                if result and isinstance(result, str):
                    ticket_ts_map[str(tid)] = result  # bot 발송 성공(ts 확보)
                elif result:
                    pass  # webhook 발송 성공(ts 없음) — 큐에서 제거
                else:
                    still_pending.append(tid)  # 발송 실패 → 큐 유지, 다음 실행 재시도
                    print(f"  -> 티켓 #{tid} 발송 실패 — 대기열 유지(재시도 예정)")
            if still_pending:
                state["overnight_queue"] = still_pending
                print(f"  야간 대기열 {len(still_pending)}건 재시도 대기")
            save_state(state)

        send_daily_summary(jwt_token)
        return

    # 기본 모드: 신규 티켓 알림 + 완료 스레드 알림
    state = load_state()

    # 1. 완료된 티켓 스레드 알림 (Bot Token 필요)
    check_and_notify_completions(jwt_token, state)

    # 2. 신규 티켓 감지
    new_tickets = find_new_tickets(jwt_token, state)
    print(f"\n신규 티켓 {len(new_tickets)}건 감지")

    ticket_ts_map = state.setdefault("ticket_ts_map", {})
    overnight_queue = state.setdefault("overnight_queue", [])
    retry_ids = set(str(tid) for tid in state.get("retry_ids", []))
    in_hours = is_business_hours()
    notified_count = 0
    queued_count = 0
    failed_count = 0

    for ticket in new_tickets:
        tid = ticket.get("id")
        str_tid = str(tid)
        assignee = ticket.get("assignedAdminUserName", "?")
        station = ticket.get("targetStationName", "?")
        # 로그 비식별: Actions 로그는 리포가 public 이면 전부 공개된다.
        # 담당자 실명·고객 사업장명은 stdout 에 남기지 않는다(티켓 ID로 커넥트에서 조회 가능).
        # Slack 알림 본문은 종전과 동일 — 발송 내용에는 영향 없음.
        print(f"  -> 티켓 #{tid}")

        if in_hours:
            # 업무시간(9~18시): 즉시 발송
            result = send_slack_notification(ticket)
            if result:
                notified_count += 1
                state["notified_ids"].append(tid)
                retry_ids.discard(str_tid)
                if isinstance(result, str):
                    ticket_ts_map[str_tid] = result
            else:
                # 발송 실패 → retry_ids에 등록, notified_ids에 추가 안 함
                retry_ids.add(str_tid)
                failed_count += 1
                print(f"     발송 실패 — 다음 실행에서 재시도 예정")
        else:
            # 업무시간 외: 야간 대기열 저장 → 다음날 9시에 발송
            overnight_queue.append(tid)
            queued_count += 1
            state["notified_ids"].append(tid)
            retry_ids.discard(str_tid)
            print(f"     업무시간 외 — 야간 대기열 추가 (다음날 9시 발송)")

    state["retry_ids"] = list(retry_ids)
    save_state(state)
    print(f"\n완료: 즉시 발송 {notified_count}건 / 야간 대기열 {queued_count}건 / 재시도 대기 {failed_count}건")

if __name__ == "__main__":
    main()
