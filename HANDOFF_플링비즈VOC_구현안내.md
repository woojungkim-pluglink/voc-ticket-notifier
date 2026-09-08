# 플링비즈 VOC 일일 알림 — 직접 구현 안내 (hand-off)

- 작성 2026-09-08 · 김우중(쿠이), PM팀
- 받는 분: 메윤
- 목적: 이 문서만으로 **본인 Claude Code에서 처음부터 세울 수 있게** 함. 제 PC·제 계정·제 저장소에 의존하지 않습니다.
- 데이터 등급: 🟡 내부 (이 문서에는 자격증명이 없습니다. 넣지도 마세요)

---

## 0. 이 문서 쓰는 법

**사람이 먼저 읽을 것**: §1 결과물 → §2 사전 준비 → **§3-0 전환 계획(중복 발송 방지)**. 준비물 4개 중 하나라도 없으면 구현이 중간에 막힙니다.

**Claude Code에 시킬 때**: 이 파일을 작업 폴더에 두고 아래처럼 말하면 됩니다.

```
HANDOFF_플링비즈VOC_구현안내.md 를 읽고 §3 절차대로 구현해줘.
§2 사전 준비가 다 됐는지 먼저 확인하고, 안 된 게 있으면 멈추고 알려줘.
§3-0 전환 계획을 지켜서, 내가 따로 말하기 전까지는 실제 게시 채널로 보내지 마.
```

§3은 사람이 읽어도 되고 Claude가 그대로 실행해도 되게 썼습니다. **§4 함정**은 제가 실제로 부딪혀 확인한 것들이니 건너뛰지 마세요 — 여기서 시간이 제일 많이 샙니다.

---

## 1. 무엇을 만드는가

평일 09:00, 자산소유주(파트너) 소유 충전소의 **미완료 VOC 티켓**을 소유주별로 집계해 Slack에 게시합니다. VOC 접수일부터 **달력일 7일** 이상 경과한 건은 별도로 나열합니다.

아래는 2026-09-08 dry-run의 **실제 출력**입니다(손으로 고치지 않았습니다).

```
📦 플링비즈 VOC 일일 현황 — 2026년 09월 08일

📌 미완료 현황 (자산소유주별)  |  전체 7건 · 5개소
   • 대한송유관공사 3건 (2개소)  ⏳3건 7일↑
   • 플러그링크(Biz_P) 2건 (1개소)
   • 한백 1건 (1개소)  ⏳1건 7일↑
   • 플러그링크(Biz_H) 1건 (1개소)  ⏳1건 7일↑

⏳ 접수 7일 경과 미완료 — 5건  (파트너 설명 대상)
   • [플러그링크(Biz_H)] #637298 [HM] 김해 낙원공원묘원(위탁) — VOC 접수 08-24 (15일 경과) · 티켓 08-31 · PROCESSING
   • [대한송유관공사] #635995 쿠팡 인천 5캠프 — VOC 접수 08-27 (12일 경과) · 티켓 08-27 · PROCESSING
   • [대한송유관공사] #637174 쿠팡 인천 5캠프 — VOC 접수 08-27 (12일 경과) · 티켓 08-31 · PROCESSING
   • [대한송유관공사] #636371 세종 나성동 복합커뮤니티센터 — VOC 접수 08-28 (11일 경과) · 티켓 08-28 · PROCESSING
   • [한백] #637824 경희골프랜드 — VOC 접수 09-01 (7일 경과) · 티켓 09-01 · PROCESSING

📊 전일(2026-09-07) 변화 — 신규 +3건 / 완료 4건
   • 플러그링크(Biz_H)  신규 +0 / 완료 1
   • 플러그링크(Biz_P)  신규 +3 / 완료 2
   • 한백  신규 +0 / 완료 1

자산소유주 7종 · 203개소 기준 · 7일은 VOC 접수일부터 달력일
```

정렬 규칙 두 가지가 다릅니다. **미완료 현황은 건수 내림차순**, **직전구간 변화는 소유주 이름 정렬**입니다(코드가 그렇게 고정). 그리고 마지막 블록의 라벨은 `es_input.json`에 `prev_label`을 넣으면 그 문자열이 그대로 쓰이고, 생략하면 `전일(prev_day)`로 나옵니다 — 월요일 실행처럼 구간이 주말을 포함할 때만 채우세요(예: `직전 보고 이후(09-04 09:00~09-07 09:00)`).

### 구조

```
Claude Code 스케줄 작업 (평일 09:00)
  └─ ES(Elasticsearch) MCP 조회 4건 → es_input.json 파일로 저장
       └─ flingbiz_daily.py  ← 집계·판정·문구·발송 전부
            ├─ 플링커넥트 REST: parentVocId → VOC 접수일
            ├─ Slack chat.postMessage → 대상 채널
            └─ flingbiz_runs.jsonl (감사 로그)
```

### 이 구조를 고른 이유 (그대로 유지 권장)

**Claude는 ES 결과를 JSON으로 옮기기만 하고, 계산·문구는 전부 파이썬이 합니다.** 숫자를 LLM이 만들면 매일 조금씩 달라지고, 틀려도 그럴듯해서 안 걸립니다. 파트너에게 나가는 숫자라 재현성이 필요해서 계산을 스크립트로 못 박았습니다. 스케줄 프롬프트에도 "집계·판정·문구 생성을 직접 하지 말 것"을 명시해 두었습니다.

---

## 2. 사전 준비 (4개 — 없으면 여기서 막힙니다)

| # | 준비물 | 확인 방법 | 없으면 |
|---|---|---|---|
| 1 | **ES MCP가 본인 Claude 계정에 붙어 있음** | Claude Code에서 `aggregate_documents` / `search_documents` 도구가 잡히는지. 안 잡히면 `ToolSearch`로 `aggregate_documents,search_documents` 검색 | 이 방식 자체가 불가. **개발팀(ES/인프라 담당)에 커넥터 연결 요청** — 필요한 건 `alias_chargers_production`·`alias_tickets_production` 읽기뿐. 또는 §8 대안 |
| 2 | **플러그링크 커넥트 admin 계정** (본인 것) | connect.pluglink.kr 로그인 가능 | VOC 접수일을 못 읽어 **경과일 판정이 전부 빠집니다**(미완료 집계는 그대로). 단 §4 ③ UTF-8 조치를 먼저 해야 WARN 출력 지점에서 죽지 않습니다 |
| 3 | **게시 채널 결정 + Slack 봇 토큰(`xoxb-`) + 그 채널에 봇 초대** | 봇 스코프 `chat:write` / 채널에서 `/invite @봇이름` / 채널ID는 Slack에서 채널명 클릭 → 팝업 맨 아래 `C0…` 복사 | 발송 불가(dry-run으로 본문 확인은 됨). **채널을 먼저 정해야 합니다 — §3-0 참조** |
| 4 | **Python 3.9+** | Windows `py -3 --version` / mac·Linux `python3 --version` | 스크립트 실행 불가. ⚠️ **Windows에서는 실행도 반드시 `py -3`** — `python3`·`python` 은 Microsoft Store 스텁으로 잡혀 "Python" 한 줄만 찍고 exit 9009로 조용히 끝납니다(제 PC 실측) |

⚠️ **2·3번은 반드시 본인 계정/본인 봇으로 발급하세요.** 제 계정이나 기존 VOC 봇 토큰을 재사용하면 감사 추적이 저와 섞이고, 제가 비밀번호를 바꾸는 순간 조용히 멈춥니다.

> 봇 초대는 잊기 쉬운데, 초대 없이 발송하면 Slack이 `not_in_channel`을 돌려줍니다(HTTP는 200이라 에러처럼 안 보입니다 — §4 ⑥).

---

## 3. 구현 절차

### 3-0. 전환 계획 — 먼저 읽어 주세요

**같은 파이프라인이 제 쪽에 이미 등록돼 있습니다.** 스케줄 작업 `flingbiz-voc-daily`(평일 **09:03** 로컬), 게시 채널 **#플링비즈알람용**. 다만 실게시 이력은 아직 없습니다(dry-run만 했고 `flingbiz_runs.jsonl` 미생성).

**같은 채널에 두 파이프라인을 동시에 켜지 마세요.** 09:00과 09:03에, 조회 시점과 로그인 계정이 다른 두 숫자가 나란히 올라갑니다.

전환 순서:

1. 메윤 dry-run으로 숫자 확인 (§3-3)
2. **본인 DM 또는 테스트 채널**로 실발송 1회 — 이 단계에서 `#플링비즈알람용`은 쓰지 않습니다
3. 요청 팀(플링비즈)에 그 수치 확인 요청
4. 제가 제 스케줄 작업 삭제·비활성 완료를 회신 — **이 회신 전에는 본 채널로 전환하지 않습니다**
5. 다음 영업일부터 메윤 작업만 `slack_channel_id`를 본 채널로 바꿔 가동

병행 관찰이 필요하면 반드시 채널을 분리하세요. 전환일 이후 발신 주체·문의 창구는 메윤입니다.

### 3-1. 폴더와 파일 3개

작업 폴더를 하나 만들고(예: `.../플링비즈-VOC알림`) 아래 3개를 둡니다. 아래 절차에서 `<작업폴더>`는 그 폴더의 **절대경로**입니다.

#### ① `flingbiz_config.json` — 판정 기준. 운영 중 바꾸는 건 이 파일뿐입니다

```json
{
  "asset_owners": [
    "플러그링크(Biz_P)",
    "플러그링크(Biz_H)",
    "한백",
    "대한송유관공사",
    "차지네틱스",
    "스칼라데이터",
    "타키온네트워크"
  ],
  "slack_channel_id": "여기에_채널ID_예_C0XXXXXXXXX",
  "slack_channel_name": "#채널명",

  "stale_threshold_days": 7,
  "stale_basis": "voc_created_at",
  "stale_day_type": "calendar",

  "completed_statuses": ["COMPLETED", "CANCELLED", "CLOSED", "DONE", "CANCELED", "FINISH", "FINISHED"],
  "require_parent_voc": true,

  "es_indices": {
    "chargers": "alias_chargers_production",
    "tickets": "alias_tickets_production"
  }
}
```

- `asset_owners`: **파트너가 늘거나 줄면 이 배열만 고칩니다.** 충전소 목록은 매 실행 ES에서 조회하므로 하드코딩하지 않습니다(신규 개시분 자동 반영). 단 **§3-2 조회 쿼리가 이 배열을 실제로 읽도록 써야** 그 약속이 지켜집니다 — §4 ⑨.
- 딜라이브는 플링비즈 포함 여부 미확정이라 1차 제외했습니다. 포함 여부는 **요청 팀이 결정할 사항**입니다.
- `completed_statuses`에 실제로 관측된 값은 `COMPLETED`·`CANCELLED` 둘뿐이고 나머지는 방어적으로 넣은 것입니다. 취소도 종결로 집계합니다.

> ⚠️ **코드가 실제로 읽는 키는 5개뿐입니다**: `asset_owners`, `slack_channel_id`, `stale_threshold_days`, `completed_statuses`, `require_parent_voc`.
> `stale_basis`·`stale_day_type`·`es_indices`·`slack_channel_name` 은 **문서용 메모라서 바꿔도 동작이 안 바뀝니다.** 특히 `stale_day_type`을 `"business"`로 바꿔도 여전히 달력일로 계산됩니다 — 영업일 기준으로 바꾸려면 `build_report()`의 `elapsed_days` 계산을 직접 고쳐야 합니다.

#### ② `flingbiz_secrets.json` — 자격증명. **절대 커밋 금지**

git을 쓴다면 **파일을 만들기 전에** `.gitignore`부터 넣으세요.

```
flingbiz_secrets.json
es_input.json
flingbiz_runs.jsonl
```

그다음 파일을 만듭니다.

```json
{
  "pluglink_email": "본인@pluglink.kr",
  "pluglink_password": "본인 비밀번호",
  "slack_bot_token": "xoxb-..."
}
```

환경변수 `PLUGLINK_EMAIL` / `PLUGLINK_PASSWORD` / `SLACK_BOT_TOKEN` 을 쓰면 이 파일 없이도 됩니다(**환경변수가 우선**).

#### ③ `flingbiz_daily.py` — 아래 전문을 그대로 저장

```python
#!/usr/bin/env python3
"""
플링비즈 VOC 일일 현황 — 결정적 계산·발송 스크립트.

역할 분담:
  - ES 조회(소유주→충전소, 티켓)는 Claude 스케줄 작업이 MCP로 수행해 es_input.json 으로 저장
  - 이 스크립트는 그 입력만 읽어 집계·판정·포맷·발송을 결정적으로 수행 (LLM 계산 없음)

사용:
  py -3 flingbiz_daily.py --input es_input.json [--dry-run]     # Windows
  python3 flingbiz_daily.py --input es_input.json [--dry-run]   # mac/Linux

종료코드: 0 정상 / 1 입력·설정 이상(발송 안 함) / 2 Slack 게시 실패
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

# Windows에서 stdout이 콘솔이 아니면(파이프·리다이렉트·Claude Code 실행) 로케일 cp949가
# 적용돼 이모지·em dash 출력에서 UnicodeEncodeError로 죽는다. 여기서 UTF-8로 고정한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
API_BASE = "https://apis.pluglink.kr/v101"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# -- 자격증명 (환경변수 우선, 없으면 flingbiz_secrets.json) -----------------
def creds():
    cfg = {}
    p = os.path.join(HERE, "flingbiz_secrets.json")
    if os.path.exists(p):
        try:
            cfg = load_json(p)
        except Exception:
            cfg = {}
    return {
        "email": os.environ.get("PLUGLINK_EMAIL") or cfg.get("pluglink_email", ""),
        "password": os.environ.get("PLUGLINK_PASSWORD") or cfg.get("pluglink_password", ""),
        "slack_token": os.environ.get("SLACK_BOT_TOKEN") or cfg.get("slack_bot_token", ""),
    }

COMMON = {
    "x-channel": "PLUGLINK", "x-platform": "WEB", "x-token": "PLUGLINK",
    "Content-Type": "application/json", "Origin": "https://connect.pluglink.kr",
    "User-Agent": "Mozilla/5.0 (compatible; FlingbizVocDaily/1.0)",
}

def api_get(url, jwt):
    req = urllib.request.Request(url, headers={**COMMON, "Authorization": f"Bearer {jwt}"}, method="GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def login(c):
    body = json.dumps({"email": c["email"], "password": c["password"],
                       "authType": "ORGANIC", "partnerId": 1}).encode("utf-8")
    hdr = {**COMMON, "x-token": "1"}
    req = urllib.request.Request(f"{API_BASE}/auths/admins/signIn", data=body, headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))["data"]["jwtToken"]

# -- 시각 정규화 (ES=UTC naive, REST=KST naive) -----------------------------
def es_utc_to_kst(s):
    """ES의 'YYYY-MM-DD HH:MM:SS'(UTC) -> KST datetime."""
    if not s:
        return None
    try:
        dt = datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(KST)

def rest_kst(s):
    """커넥트 REST의 'YYYY-MM-DD HH:MM:SS'(이미 KST) -> KST datetime."""
    if not s:
        return None
    try:
        dt = datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=KST)

# -- Slack ----------------------------------------------------------------
def slack_post(token, channel, blocks, text, dry):
    if dry:
        print(f"  [DRY-RUN] slack chat.postMessage -> {channel}")
        print("  " + text.replace("\n", "\n  ")[:1500])
        return "DRYRUN"
    payload = {"channel": channel, "text": text, "blocks": blocks}
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.loads(r.read().decode("utf-8"))
    if not res.get("ok"):
        # Slack은 실패도 HTTP 200으로 준다. ok 필드를 반드시 본다.
        print(f"  [ERROR] Slack 발송 실패: {res.get('error')}")
        return None
    return res.get("ts")

# -- 본 계산 --------------------------------------------------------------
def build_report(cfg, data, jwt, quiet=False):
    owners = data.get("owners") or {}
    station_owner = {}
    for owner, sids in owners.items():
        for sid in sids:
            station_owner[int(sid)] = owner

    done_set = set(cfg["completed_statuses"])
    threshold = int(cfg["stale_threshold_days"])
    asof = data.get("asof_kst") or datetime.now(KST).strftime("%Y-%m-%d")
    asof_date = datetime.strptime(asof, "%Y-%m-%d").date()

    def owner_of(t):
        return station_owner.get(int(t["targetStationId"])) if t.get("targetStationId") else None

    # 1) 미완료 현황
    open_rows = []
    for t in data.get("open_tickets") or []:
        if cfg.get("require_parent_voc") and not t.get("parentVocId"):
            continue
        if t.get("status") in done_set:
            continue
        o = owner_of(t)
        if not o:
            continue
        open_rows.append({**t, "owner": o})

    # 2) VOC 접수일 조회 (미완료 건만) -> 경과일(달력일) 계산
    voc_cache = {}
    for r in open_rows:
        vid = r.get("parentVocId")
        if vid in voc_cache:
            r["voc_created"] = voc_cache[vid]
            continue
        vc = None
        if jwt:
            try:
                v = api_get(f"{API_BASE}/crms/vocs/{vid}", jwt).get("data") or {}
                vc = rest_kst(v.get("createdAt"))
            except Exception as e:
                if not quiet:
                    print(f"  [WARN] VOC {vid} 조회 실패: {str(e)[:60]}")
        voc_cache[vid] = vc
        r["voc_created"] = vc
    for r in open_rows:
        vc = r.get("voc_created")
        r["elapsed_days"] = (asof_date - vc.date()).days if vc else None

    stale = sorted([r for r in open_rows if r["elapsed_days"] is not None and r["elapsed_days"] >= threshold],
                   key=lambda r: -r["elapsed_days"])
    unknown = [r for r in open_rows if r["elapsed_days"] is None]

    # 3) 직전 구간 변화
    def by_owner_count(rows):
        # parentVocId 필터는 ES 쿼리(exists parentVocId)에서 이미 적용된다.
        # 충전소별 집계 형태({"targetStationId": X, "count": N})도 허용.
        c = {}
        for t in rows or []:
            o = owner_of(t)
            if o:
                c[o] = c.get(o, 0) + int(t.get("count", 1))
        return c
    prev_new = by_owner_count(data.get("prev_new"))
    prev_done = by_owner_count(data.get("prev_done"))

    # 4) 소유주별 미완료 집계
    agg = {}
    for r in open_rows:
        a = agg.setdefault(r["owner"], {"cnt": 0, "stations": set(), "stale": 0})
        a["cnt"] += 1
        a["stations"].add(r["targetStationId"])
        if r["elapsed_days"] is not None and r["elapsed_days"] >= threshold:
            a["stale"] += 1

    return {
        "asof": asof, "asof_date": asof_date, "owners": owners,
        "open_rows": open_rows, "stale": stale, "unknown": unknown,
        "agg": agg, "prev_new": prev_new, "prev_done": prev_done,
        "prev_day": data.get("prev_day"),
        "prev_label": data.get("prev_label"),
        "station_count": sum(len(v) for v in owners.values()),
    }

def render(cfg, rep):
    thr = cfg["stale_threshold_days"]
    d = datetime.strptime(rep["asof"], "%Y-%m-%d")
    head = f"📦 플링비즈 VOC 일일 현황 — {d.strftime('%Y년 %m월 %d일')}"
    lines = [head, ""]

    total_open = len(rep["open_rows"])
    total_st = len({r["targetStationId"] for r in rep["open_rows"]})
    lines.append(f"📌 *미완료 현황* (자산소유주별)  |  전체 *{total_open}건* · {total_st}개소")
    if rep["agg"]:
        for owner, a in sorted(rep["agg"].items(), key=lambda kv: -kv[1]["cnt"]):
            tail = f"  ⏳{a['stale']}건 {thr}일↑" if a["stale"] else ""
            lines.append(f"   • {owner} *{a['cnt']}건* ({len(a['stations'])}개소){tail}")
    else:
        lines.append("   • 미완료 없음")
    lines.append("")

    lines.append(f"⏳ *접수 {thr}일 경과 미완료* — {len(rep['stale'])}건  _(파트너 설명 대상)_")
    if rep["stale"]:
        for r in rep["stale"][:20]:
            vc = r["voc_created"].strftime("%m-%d") if r.get("voc_created") else "?"
            tc = es_utc_to_kst(r.get("createdAt"))
            tcs = tc.strftime("%m-%d") if tc else "?"
            lines.append(f"   • [{r['owner']}] #{r['id']} {r.get('targetStationName') or '-'}"
                         f" — VOC 접수 {vc} (*{r['elapsed_days']}일 경과*) · 티켓 {tcs} · {r.get('status')}")
        if len(rep["stale"]) > 20:
            lines.append(f"   … 외 {len(rep['stale']) - 20}건")
    else:
        lines.append("   • 해당 없음")
    if rep["unknown"]:
        lines.append(f"   ⚠️ VOC 접수일 조회 실패 {len(rep['unknown'])}건 — 경과일 판정 제외")
    lines.append("")

    # 라벨: 스케줄러가 조회 구간을 명시적으로 넘기면 그대로 쓴다(월요일·실행 누락 시 구간이 벌어짐).
    label = rep.get("prev_label") or f"전일({rep.get('prev_day') or '-'})"
    tn, td = sum(rep["prev_new"].values()), sum(rep["prev_done"].values())
    lines.append(f"📊 *{label} 변화* — 신규 +{tn}건 / 완료 {td}건")
    ks = sorted(set(rep["prev_new"]) | set(rep["prev_done"]))
    if ks:
        for o in ks:
            lines.append(f"   • {o}  신규 +{rep['prev_new'].get(o, 0)} / 완료 {rep['prev_done'].get(o, 0)}")
    else:
        lines.append("   • 변화 없음")
    lines.append("")
    lines.append(f"_자산소유주 {len(rep['owners'])}종 · {rep['station_count']}개소 기준 · "
                 f"{thr}일은 VOC 접수일부터 달력일_")

    text = "\n".join(lines)
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": head, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines[2:])[:2900]}},
    ]
    return text, blocks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(HERE, "es_input.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = load_json(os.path.join(HERE, "flingbiz_config.json"))
    if not os.path.exists(a.input):
        print(f"[ERROR] 입력 파일 없음: {a.input} (ES 조회 결과가 필요합니다)")
        sys.exit(1)
    data = load_json(a.input)

    # 안전장치 1: 입력이 비정상이면 발송하지 않는다
    owners = data.get("owners") or {}
    if not owners or sum(len(v) for v in owners.values()) == 0:
        print("[ERROR] owners(소유주->충전소) 매핑이 비어 있음 — 오발송 방지로 중단")
        sys.exit(1)

    # 안전장치 2: ES 쿼리에 실제로 쓴 기준이 config와 다르면 중단
    # (config만 고쳐도 반영된다는 약속을 지키기 위한 대조. 필드가 없으면 경고만)
    qo = data.get("query_owners")
    if qo is not None and sorted(qo) != sorted(cfg["asset_owners"]):
        print(f"[ERROR] ES 조회에 쓴 소유주가 config와 다름 — 게시 중단\n"
              f"        조회: {sorted(qo)}\n        config: {sorted(cfg['asset_owners'])}")
        sys.exit(1)
    qs = data.get("query_completed_statuses")
    if qs is not None and sorted(qs) != sorted(cfg["completed_statuses"]):
        print(f"[ERROR] ES 조회에 쓴 종결상태가 config와 다름 — 게시 중단\n"
              f"        조회: {sorted(qs)}\n        config: {sorted(cfg['completed_statuses'])}")
        sys.exit(1)
    if qo is None or qs is None:
        print("[WARN] es_input.json에 query_owners/query_completed_statuses가 없어 기준 대조를 건너뜁니다")

    missing = [o for o in cfg["asset_owners"] if o not in owners]
    if missing:
        print(f"[WARN] 설정에 있으나 ES 조회 결과에 없는 소유주: {missing}")

    c = creds()
    jwt = None
    if not c["email"] or not c["password"]:
        print("[WARN] 플링커넥트 자격증명 없음 — VOC 접수일 조회를 건너뜁니다(경과일 판정 불가)")
    else:
        try:
            jwt = login(c)
        except Exception as e:
            print(f"[WARN] 로그인 실패({str(e)[:60]}) — 경과일 판정 제외")

    rep = build_report(cfg, data, jwt)
    text, blocks = render(cfg, rep)

    if not c["slack_token"] and not a.dry_run:
        print("[ERROR] SLACK_BOT_TOKEN 없음 — 발송 중단")
        sys.exit(1)
    ts = slack_post(c["slack_token"], cfg["slack_channel_id"], blocks, text, a.dry_run)

    # 감사 로그 (재현·대조용)
    log = {
        "ran_at": datetime.now(KST).isoformat(),
        "asof": rep["asof"], "dry_run": bool(a.dry_run), "slack_ts": ts,
        "owners": len(rep["owners"]), "stations": rep["station_count"],
        "open_total": len(rep["open_rows"]),
        "open_by_owner": {k: v["cnt"] for k, v in rep["agg"].items()},
        "stale_total": len(rep["stale"]),
        "voc_lookup_failed": len(rep["unknown"]),
        "prev_day": rep.get("prev_day"),
        "prev_new": rep["prev_new"], "prev_done": rep["prev_done"],
    }
    if not a.dry_run:
        with open(os.path.join(HERE, "flingbiz_runs.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")
    print("\n[결과] " + json.dumps(log, ensure_ascii=False))

    # 게시 실패를 종료코드로 드러낸다 (0으로 끝나면 미게시가 성공으로 기록된다)
    if not a.dry_run and ts is None:
        print("[ERROR] Slack 게시 실패 — 감사 로그에 slack_ts:null 기록. 종료코드 2")
        sys.exit(2)

if __name__ == "__main__":
    main()
```

### 3-2. ES 조회 4건 → `es_input.json`

여기는 Claude가 MCP로 수행하는 부분입니다. 인덱스는 `alias_chargers_production`(충전기, 실시간)과 `alias_tickets_production`(티켓).

> **아래 쿼리의 소유주·종결상태 값은 반드시 `flingbiz_config.json`에서 읽어 넣으세요.** 문서에 적힌 7종은 2026-09-08 시점 값을 보여주는 예시일 뿐입니다. 리터럴로 박으면 config만 고쳐도 반영되지 않습니다(§4 ⑨). 그리고 실제로 쓴 값을 `es_input.json`의 `query_owners`·`query_completed_statuses`에 그대로 기록하면 스크립트가 config와 대조해 어긋날 때 발송을 막아 줍니다.

**조회 ① 자산소유주 → 충전소 매핑** (`aggregate_documents`)

```
index: alias_chargers_production
query: {"terms": {"owner.partnerName": [ ...config의 asset_owners 배열 그대로... ]}}
aggs:  {"by_owner": {"terms": {"field": "owner.partnerName", "size": 20},
        "aggs": {"stations": {"terms": {"field": "station.id", "size": 500}}}}}
size: 0
```

이 결과가 대상 충전소 전체입니다. 2026-09-08 기준 **203개소 · 충전기 776대**(응답의 `total`이 충전기 수).

**조회 ② 미완료 티켓** (`search_documents`)

```
index: alias_tickets_production
size:  500        ← 7건뿐이어도 여유를 둡니다. 이유는 아래
query: {"bool": {
  "filter": [
    {"exists": {"field": "parentVocId"}},
    {"terms": {"targetStationId": [ ...①의 station.id 전체... ]}}
  ],
  "must_not": [{"terms": {"status": [ ...config의 completed_statuses 그대로... ]}}]
}}
```

히트에서 **6개 필드만** 추립니다: `id`, `parentVocId`, `createdAt`, `status`, `targetStationId`, `targetStationName`.

> 응답의 `total`과 실제로 `open_tickets`에 옮긴 건수를 **반드시 비교하세요.** 다르면 `size` 상한에 걸려 잘린 것이므로 **게시하지 말고 보고**합니다. 파트너가 늘면 조용히 잘리는 지점입니다.

**조회 ③④ 직전 구간 신규/완료** (`aggregate_documents`, size 0)

구간은 **직전 영업일 09:00 KST ~ 오늘 09:00 KST**. 여기서 영업일은 **주말(토·일)만 제외**하고 공휴일은 영업일로 취급합니다(cron이 `0 9 * * 1-5`라 공휴일에도 실행되어 그날 보고가 나가 있으므로).

**실행이 밀렸으면 구간을 넓혀야 합니다.** `flingbiz_runs.jsonl` 마지막 `dry_run:false` 줄의 `asof`가 직전 영업일보다 이전이면(= 그 사이 실행이 빠졌으면) 구간 시작을 그 `asof` 09:00으로 넓히고, `prev_day`와 `prev_label`에 반영하세요. 안 하면 밀린 날의 신규·완료가 어떤 보고에도 안 나옵니다(§4 ⑧).

KST 09:00 = 같은 날 UTC 00:00이라 ES에 넘길 문자열은 날짜만 갈아끼우면 됩니다.

```
③ 신규:  filter에 {"range": {"createdAt":   {"gte": "구간시작일 00:00:00", "lt": "오늘 00:00:00"}}}
④ 완료:  filter에 {"range": {"completedAt": {"gte": "구간시작일 00:00:00", "lt": "오늘 00:00:00"}}}
공통:    {"exists": {"field": "parentVocId"}} + {"terms": {"targetStationId": [...전체...]}}
aggs:    {"st": {"terms": {"field": "targetStationId", "size": 300}}}
```

버킷을 `{"targetStationId": <key>, "count": <doc_count>}` 형태로 옮깁니다.

**결과를 `es_input.json`으로 저장** (문자열은 ES 원본 그대로, 가공 금지)

```json
{
  "generated_at": "<지금 ISO8601 +09:00>",
  "asof_kst": "<오늘 YYYY-MM-DD>",
  "prev_day": "<구간 시작일 YYYY-MM-DD>",
  "prev_label": "<구간이 전일이 아닐 때만: 직전 보고 이후(09-04 09:00~09-08 09:00)>",
  "query_owners": [ "...실제 조회에 쓴 소유주 배열..." ],
  "query_completed_statuses": [ "...실제 조회에 쓴 종결상태 배열..." ],
  "owners": { "<소유주명>": [10030649, 10028515] },
  "open_tickets": [
    {"id": 641369, "parentVocId": 447011, "createdAt": "2026-09-07 09:06:11",
     "status": "PROCESSING", "targetStationId": 10030649, "targetStationName": "검단신도시 예미지더시그너스"}
  ],
  "prev_new":  [ {"targetStationId": 10030649, "count": 3} ],
  "prev_done": [ {"targetStationId": 10029212, "count": 1} ]
}
```

### 3-3. 검증 (발송 전 필수)

```bash
# Windows
py -3 -X utf8 "<작업폴더>\flingbiz_daily.py" --input "<작업폴더>\es_input.json" --dry-run

# mac / Linux
python3 "<작업폴더>/flingbiz_daily.py" --input "<작업폴더>/es_input.json" --dry-run
```

`-X utf8`이 없으면 Windows에서 이모지·em dash 출력 지점에 `UnicodeEncodeError`로 죽습니다(§4 ③). 스크립트 안에 `reconfigure` 방어를 넣어 뒀지만, 옵션까지 주는 게 확실합니다.

dry-run은 **발송하지 않고 감사 로그도 남기지 않습니다**. 확인할 것:

- `[DRY-RUN] slack chat.postMessage -> …` 에 찍힌 값이 `여기에_`로 시작하지 않는 **실제 채널 ID**인가
- `owners`의 충전소 합계(`stations`)가 **203** 근처인가 (파트너 증감에 따라 변합니다)
- `voc_lookup_failed`가 0인가 (0이 아니면 커넥트 로그인 문제)
- 경과일이 **티켓 생성일이 아니라 VOC 접수일** 기준으로 나오는가 (§4 ②)
- 소유주별 합계가 전체 건수와 맞는가
- `[WARN] … 기준 대조를 건너뜁니다` 가 떴다면 `query_owners`를 안 넣은 것 — 넣는 편이 안전합니다

숫자가 납득되면 `--dry-run`을 빼고 실행합니다. 단 **첫 실발송은 본인 DM/테스트 채널로** (§3-0).

### 3-4. 스케줄 작업 등록

Claude Code에서 `create_scheduled_task`로 등록합니다. cron은 **로컬 시간대** 기준이라 그대로 `0 9 * * 1-5`.

프롬프트는 **새 세션에서 아무 기억 없이 실행돼도 되게 자기완결적으로** 써야 합니다. 아래를 골격으로 쓰고, §3-2의 쿼리 4건을 프롬프트 안에 그대로 박아 넣으세요.

```
플링비즈 VOC 일일 현황을 산출해 Slack <채널명>에 게시한다.

## 절대 금지
- 집계·판정·문구 생성을 직접 하지 말 것. 숫자와 문장은 반드시 flingbiz_daily.py가 만든다.
  너의 역할은 ES 조회 결과를 JSON으로 옮기는 것까지다.
- Slack에 직접 메시지를 보내지 말 것. 게시는 스크립트가 한다.

## 작업 폴더
<본인 폴더 절대경로>

## 도구
ES는 계정에 붙은 MCP로 조회한다(aggregate_documents, search_documents).
도구가 로드되지 않았으면 ToolSearch로 먼저 불러온다.
함정: ES의 createdAt/completedAt은 UTC naive 문자열이다. 스크립트가 정규화하므로
가공하지 말고 그대로 옮겨라.

## 절차
1. flingbiz_config.json의 asset_owners와 completed_statuses를 읽는다.
   ES 쿼리의 terms/must_not에는 반드시 이 배열을 넣는다(문서의 예시 값을 그대로 쓰지 말 것).
   실제로 쓴 값을 es_input.json의 query_owners / query_completed_statuses에 기록한다.
   충전소 목록은 하드코딩하지 않는다.
2~5. (§3-2의 조회 ①②③④를 쿼리째로 여기에 붙여넣기) → es_input.json 작성
   - 조회 ②는 응답 total과 옮긴 건수를 비교한다.
   - 직전 구간은 flingbiz_runs.jsonl 마지막 dry_run:false 줄의 asof를 보고,
     실행이 밀렸으면 구간 시작을 그 날짜로 넓히고 prev_label에 실제 구간을 쓴다.
6. 실행 (스케줄 실행은 cwd가 보장되지 않으니 반드시 절대경로):
   - Windows: py -3 -X utf8 "<폴더 절대경로>\flingbiz_daily.py" --input "<폴더 절대경로>\es_input.json"
   - mac/Linux: python3 "<폴더 절대경로>/flingbiz_daily.py" --input "<폴더 절대경로>/es_input.json"

## 중단 조건 (게시하지 말고 보고만)
- ES 조회 실패 또는 MCP 사용 불가
- 소유주 매핑이 비었거나 충전소 합계가 0
- 조회 ②의 total과 open_tickets 건수 불일치(size 상한에 걸려 잘림)
- 충전소 합계가 직전 실행 대비 20% 이상 급변 (flingbiz_runs.jsonl 마지막 줄의 stations와 비교)

## 보고
소유주 N종·N개소 / 미완료 N건(N개소) / 7일 경과 N건 / Slack ts 또는 중단 사유 /
스크립트 종료코드(2면 게시 실패) / [WARN] 줄이 있으면 그대로 전달 /
voc_lookup_failed가 0이 아니면 건수와 티켓 ID

## 참고 기준값
2026-09-08 실측: 7종·203개소·776대(한백 74 / 스칼라데이터 51 / 플러그링크(Biz_P) 34 /
플러그링크(Biz_H) 20 / 대한송유관공사 12 / 타키온네트워크 10 / 차지네틱스 2),
미완료 7건·5개소, 7일 경과 5건. 이 규모와 크게 다르면 조회 조건을 먼저 의심할 것.
```

등록 후 권한 승인을 위해 한 번 수동 실행("Run now")하되, **프롬프트 6단계 명령에 `--dry-run`을 붙인 상태로** 돌리세요. 그때 ES MCP·Bash 권한이 승인되어 저장되고, 실제 게시는 다음 정시 실행에 맡깁니다.

> ⚠️ **중복 발송 가드가 없습니다.** 같은 날 두 번 실발송하면 동일 본문이 두 번 올라갑니다(직전구간 수치까지 그대로 반복). §3-3에서 이미 실발송했다면 그날은 다시 발송하지 마세요.

---

## 4. 함정 (실측 확인 — 여기서 시간이 샙니다)

### ① 자산소유주는 REST에 필드가 없습니다 — ES만 유일한 출처

커넥트 REST(`/crms/tickets`, `/crms/vocs`)로는 소유주를 못 갈라냅니다. 파트너 관련 필드가 `cpoName`·`assignedPartnerName`·`createdPartnerName` 셋뿐이고, **조회한 1,091건 전수가 "플러그링크"(운영사)** 라서 대상 소유주 7종과 **0건 일치**합니다.

| 대안 | 결과 |
|---|---|
| 커넥트 REST | 소유주 필드 없음 (위) |
| 백오피스 `/chargers/backoffices/stations` | 소유주 있으나 헤드리스 인증으로 **HTTP 401** — 브라우저 세션 필요 |
| ES `station_production` | `station.owner_partner_name` 있으나 **월 스냅샷**(최신 2026-08-01) → 8월 이후 신규 충전소 누락, **티켓 34건 미탐지** 실측 |
| ES `alias_chargers_production` | **실시간. `owner.partnerName`(keyword) 보유. 요청 팀 실측치 203개소·776대를 정확히 재현** ✅ |

`station_production`이 이름은 그럴듯한데 월 스냅샷입니다. 저는 이걸로 먼저 만들었다가 **티켓 건수가 149로 나와** 요청 팀 실측 183과 어긋났고, 원인 찾는 데 시간을 썼습니다. **`alias_chargers_production`만 쓰세요.**

### ② 경과일은 티켓 생성일이 아니라 VOC 접수일 기준

같은 VOC에서 티켓이 나중에 파생되므로, 티켓 생성일로 재면 실제 지연이 짧게 나옵니다.

- #637298(플러그링크(Biz_H)): 티켓 08-31 → 8일처럼 보이지만, VOC 접수 08-24 → **15일**

그래서 스크립트가 미완료 건마다 `parentVocId`로 `/crms/vocs/{id}`를 조회해 접수일을 가져옵니다. **영업일이 아니라 달력일** 기준입니다(요청 팀 합의).

### ③ Windows에서 `python3`도, 한글 출력도 조용히 터집니다

두 가지가 겹칩니다.

1. **`python3`·`python` 은 Microsoft Store 스텁**으로 잡혀 `"Python"` 한 줄만 찍고 **exit 9009**로 끝납니다(제 PC 실측). 정상 실행은 `py -3` 뿐입니다.
2. stdout이 콘솔이 아니면(파이프·리다이렉트, **Claude Code가 실행해 출력을 캡처하는 경우**) 로케일 `cp949`가 적용돼 `📦`·`—` 출력 지점에서 `UnicodeEncodeError`로 죽습니다. 실측: `UnicodeEncodeError: 'cp949' codec can't encode character '—'`.

즉 **문서 절차의 주 실행 경로가 정확히 이 조건**입니다. `py -3 -X utf8`로 돌리고, 스크립트의 `sys.stdout.reconfigure` 3줄을 지우지 마세요.

### ④ ES는 UTC, 커넥트 REST는 KST — 섞으면 9시간 밀립니다

- ES `createdAt`/`completedAt` = `"2026-09-07 09:06:11"` **(UTC, 타임존 표기 없음)**
- 커넥트 REST `createdAt` = 같은 모양인데 **KST**

생김새가 똑같아서 눈으로 구분이 안 됩니다. 스크립트의 `es_utc_to_kst()` / `rest_kst()`가 각각 처리하니, **ES 값은 절대 가공하지 말고 원본 문자열로** `es_input.json`에 넣으세요.

### ⑤ 티켓 status는 5종 — `completedAt` 결측은 최근 데이터에선 문제 안 됩니다

실측 enum: `RECEIVED` / `PROCESSING` / `MONITORING` / `COMPLETED` / `CANCELLED`.

`completedAt` 결측률을 ES로 실측하면(`status:COMPLETED` + `parentVocId` 존재 기준):

| 범위 | 전체 | `completedAt` 있음 | 결측률 |
|---|---|---|---|
| 전체 이력 | 209,129 | 176,770 | **15.5%** |
| 2026-07-01 이후 생성분 | 31,692 | 31,684 | **0.03%** (8건) |

즉 결측은 과거 데이터 현상이고, **일일 구간 집계(최근 며칠)에는 사실상 영향이 없습니다.** 오래된 건을 소급 집계할 때만 주의하세요. (기존 VOC 봇은 REST 응답 기준으로 결측을 훨씬 많이 관측했는데, REST 목록 응답과 ES 색인 필드는 다른 출처라 수치가 다릅니다.)

### ⑥ `targetStationId = 0`인 티켓이 있습니다

미완료 티켓 전체 624건 중 **14건이 station id 0**(충전소 미지정)입니다. 소유주 매핑에서 자동 탈락하지만, 전체 수치를 대조할 때 "왜 합이 안 맞지"의 원인이 됩니다.

### ⑦ Slack은 실패해도 HTTP 200

`chat.postMessage`는 봇이 채널에 없으면 `{"ok": false, "error": "not_in_channel"}`을 **HTTP 200으로** 돌려줍니다. 스크립트는 `res["ok"]`를 확인하고, 실패 시 **종료코드 2**로 끝냅니다(그래야 미게시가 성공으로 기록되지 않습니다). 직접 손댈 때도 `ok`를 같이 보세요.

### ⑧ 스케줄 작업은 Claude 앱이 열려 있을 때만 돕니다 — 밀리면 구간에 구멍이 납니다

닫혀 있으면 그 시각 실행이 밀려 **다음 앱 실행 때 1회** 수행됩니다. 정시가 보장되지 않습니다(§8).

더 조용한 문제는 **구간 누락**입니다. 직전 구간을 달력으로만 계산하면, 실행이 빠진 날의 신규·완료는 어떤 보고에도 나오지 않습니다. `flingbiz_runs.jsonl` 마지막 `asof`를 보고 구간 시작을 그 날짜로 넓히고, 라벨에 실제 구간을 쓰세요(예: `직전 보고 이후(09-04 09:00~09-08 09:00)`).

### ⑨ `completed_statuses`는 ES 쿼리의 `must_not`과 한 몸입니다

config에서 어떤 status를 빼서 "미완료로 보겠다"고 바꿔도, **ES 쿼리의 `must_not`이 여전히 그 status를 걸러내면 해당 티켓은 입력에 아예 들어오지 않습니다.** 스크립트는 없는 티켓을 알 방법이 없습니다. 같은 이유로 `asset_owners`에 파트너를 추가해도 쿼리가 옛 목록을 쓰면 그 파트너는 조용히 빠집니다.

그래서 §3-2가 "config에서 읽어 넣어라"라고 못 박고, `query_owners`·`query_completed_statuses` 대조 장치를 둔 것입니다. 이 두 필드를 넣어 두면 어긋날 때 발송이 막힙니다.

---

## 5. 안전장치 (이 부분은 지우지 마세요)

| 상황 | 동작 | 왜 |
|---|---|---|
| 소유주 매핑이 빈 결과 | 스크립트가 발송 중단(`exit 1`) | ES가 빈 값을 주면 "미완료 0건"이 **정상처럼** 게시됩니다. 파트너에게 나가는 숫자라 이게 가장 위험 |
| 쿼리에 쓴 소유주·종결상태가 config와 불일치 | 발송 중단(`exit 1`) | "config만 고치면 반영된다"는 약속을 실제로 보장 (§4 ⑨) |
| Slack 게시 실패(`ok:false`) | 로그에 `slack_ts:null` 남기고 **`exit 2`** | 종료코드 0이면 미게시가 성공으로 기록돼 감시가 실패를 못 잡습니다 |
| 조회 ②의 `total` ≠ 옮긴 건수 | 스케줄러가 중단 후 보고 | `size` 상한에 걸려 조용히 잘리는 것 방지 |
| 충전소 수 20% 이상 급변 | 스케줄러가 중단 후 보고 | 인덱스 이상·소유주명 변경 조기 감지 |
| VOC 접수일 조회 실패 | 해당 건 경과일 판정 제외 + 메시지에 "⚠️ 조회 실패 N건" 표기 | 조용히 빠지면 7일 경과 건이 숨습니다 |
| 설정에 있으나 ES에 없는 소유주 | `[WARN]` 표기하고 계속 | 오탈자·계약 종료 감지 |
| 같은 날 재실행 | **차단 장치 없음 — 동일 메시지 중복 게시** | 발송 전 `flingbiz_runs.jsonl` 마지막 줄의 `asof`를 확인하세요 |
| 실행마다 `flingbiz_runs.jsonl` 기록 | 사후 대조·급변 판정·구간 보정 근거 | dry-run은 기록하지 않음 |

"0건"은 데이터가 없는 게 아니라 조회 조건이 틀린 경우가 훨씬 많습니다. 0이 나오면 조건을 먼저 의심하세요.

---

## 6. 바꾸는 방법

| 바꿀 것 | 어디 | 주의 |
|---|---|---|
| 파트너 추가/제거 (딜라이브 포함 등) | `flingbiz_config.json` → `asset_owners` | ES 쿼리가 config를 읽고 있어야 반영됨 (§4 ⑨) |
| 경과 임계일 (7일 → N일) | `stale_threshold_days` | 코드가 읽음 ✅ |
| 게시 채널 | `slack_channel_id` | 코드가 읽음 ✅ (`slack_channel_name`은 메모용) |
| 종결로 볼 status | `completed_statuses` | ES `must_not`과 함께 바뀌어야 함 (§4 ⑨) |
| 실행 시각 | 스케줄 작업의 cron | 로컬 시간대 |
| 영업일 기준으로 경과일 계산 | **코드 수정 필요** | `stale_day_type`을 바꿔도 안 됩니다 — `build_report()`의 `elapsed_days` 계산을 고쳐야 함 |

충전소 목록은 어디에도 없습니다(매 실행 ES 조회). 신규 개시분이 자동 반영되는 게 이 설계의 요점입니다.

---

## 7. 막혔을 때

| 증상 | 원인 | 조치 |
|---|---|---|
| `"Python"` 한 줄 찍고 exit 9009 | Windows에서 `python3`/`python`이 Store 스텁 | `py -3`로 실행 (§4 ③) |
| `UnicodeEncodeError: 'cp949' codec can't encode character '—'` | 출력이 파이프/파일이라 로케일 cp949 적용 | `py -3 -X utf8` 로 실행, 또는 스크립트의 `reconfigure` 3줄 확인 (§4 ③) |
| `[ERROR] 입력 파일 없음` | 스케줄 실행의 cwd가 작업 폴더가 아님 | 실행 명령을 **절대경로**로 (§3-4 6단계) |
| `aggregate_documents` 도구가 없다 | ES MCP 미연결 | `ToolSearch`로 검색 → 없으면 개발팀에 커넥터 요청 |
| 미완료 0건인데 그럴 리 없다 | 소유주명 오탈자, 인덱스 오타 | 조회 ①만 단독 실행해 `total`이 776 근처인지 확인 |
| 티켓 건수가 실측보다 적다 (예: 149 vs 183) | `station_production`(월 스냅샷)을 썼다 | `alias_chargers_production`으로 교체 (§4 ①) |
| 경과일이 예상보다 짧다 | 티켓 생성일로 계산했다 | VOC 접수일 기준인지 확인 (§4 ②) |
| 날짜가 9시간 밀렸다 | ES(UTC)와 REST(KST)를 섞었다 | §4 ④ |
| `voc_lookup_failed`가 전건 | 커넥트 로그인 실패 | 계정·비밀번호 확인. 미완료 집계는 그대로 나옵니다 |
| Slack이 조용히 안 온다 | `not_in_channel` | 채널에 봇 초대 (§4 ⑦). **종료코드 2와 로그의 `slack_ts:null`로 확인** |
| 파트너를 추가했는데 안 나온다 | 쿼리가 옛 소유주 목록을 쓰고 있다 | `query_owners` 대조 장치 확인 (§4 ⑨) |
| 09:00에 안 왔다 | 앱이 닫혀 있었다 | §4 ⑧ — 다음 실행 때 1회 발송. 구간 보정도 확인 |

---

## 8. 한계와 대안

**지금 방식(Claude Code 스케줄러 + ES MCP)**
- 장: 개발팀에 **별도 ES 권한 요청이 필요 없음**. 즉시 시작 가능
- 단: **Claude 앱이 열려 있어야 실행**. 정시 보장 안 됨, 밀리면 구간 보정 필요

**상시 실행이 필요해지면**: ES 읽기 전용 권한(엔드포인트 + API key)을 받아 GitHub Actions로 옮기면 됩니다. 개발팀 요청서 초안을 제가 써 두었으니(`플링비즈_ES접근요청.md`) 필요하면 드리겠습니다. 필요한 건 인덱스 2개 읽기 권한뿐이고, 부하는 회당 쿼리 2~4건입니다.

**요청 팀에 반드시 고지할 것** (제가 아직 안 했습니다 — 전환 시 메윤이 해 주세요):
1. 09:00 정시가 보장되지 않는다는 점(앱이 닫혀 있으면 밀림)
2. 직전 구간 완료 수치는 `completedAt` 기준이라는 점(최근 데이터에선 영향 미미 — §4 ⑤)
3. 1차는 일일 요약만이고 실시간 알림은 미구현이라는 점

**요청 팀이 결정할 사항**: 딜라이브 포함 여부, 실시간 알림 도입 여부, 게시 채널.

**틀린 숫자가 나갔을 때**: 해당 메시지를 삭제하지 말고 같은 스레드에 정정 코멘트를 답니다(파트너 협의 근거로 쓰이므로 이력이 남아야 합니다). `flingbiz_runs.jsonl`의 해당 `ran_at` 줄이 그 시점 조회 결과이므로 원인 추적의 출발점입니다.

---

## 9. 다른 기준으로 재사용할 때

이 구조에서 재사용 가치가 있는 건 **"ES에만 있는 속성으로 티켓을 갈라내는 조인 패턴"** 입니다.

```
속성(소유주·지역·모델·CPO 등) → alias_chargers_production 에서 station.id 목록
  → alias_tickets_production 의 targetStationId 로 티켓 필터
    → 파이썬이 집계·판정·발송
```

소유주 자리에 다른 필드를 넣으면 그대로 동작합니다. 계산을 LLM이 아니라 스크립트가 하는 분업, 그리고 §5 안전장치는 기준이 뭐든 유지하시길 권합니다.

같은 패턴의 일반화된 템플릿 저장소(`scheduled-automation-template`)도 있습니다. 필요하면 접근 권한 드리겠습니다.

---

## 10. 인수 완료 기준

아래 5개가 되면 "제대로 돌고 있다"고 말할 수 있습니다.

1. dry-run 출력의 `stations`가 203 근처, `voc_lookup_failed` = 0
2. 요청 팀이 미완료 건수·7일 경과 목록을 확인해 "맞다"고 회신
3. 테스트 채널 실발송에서 종료코드 0, `flingbiz_runs.jsonl`에 `slack_ts` 값이 남음
4. 제 스케줄 작업 비활성 회신을 받은 뒤 본 채널로 전환 (§3-0)
5. 전환 후 2영업일 연속 정상 게시 확인

---

## 11. 참고

- 제 쪽 운영 문서: `플링비즈_VOC_일일현황.md`
- 기존 VOC 티켓 알림 봇(담당자 배분 기준)의 업무 품질기준: `QUALITY_STANDARD.md`
- 이 문서는 6개 관점(재현성·스크립트·ES쿼리·보안·수치정합·운영이관) 검수를 거쳐 확정 지적 14건을 반영한 판입니다.
- 막히면 저에게 연락 주세요 — 김우중
