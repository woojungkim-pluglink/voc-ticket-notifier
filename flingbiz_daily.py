#!/usr/bin/env python3
"""
플링비즈 VOC 일일 현황 — 결정적 계산·발송 스크립트.

역할 분담:
  - ES 조회(소유주→충전소, 티켓)는 Claude 스케줄 작업이 MCP로 수행해 es_input.json 으로 저장
  - 이 스크립트는 그 입력만 읽어 **집계·판정·포맷·발송**을 결정적으로 수행 (LLM 계산 없음)

기존 VOC 봇(ticket_notifier.py / ticket_config.json)은 일절 수정하지 않으며 import 하지도 않는다.
자격증명은 ticket_config.json 을 읽기 전용으로 재사용하거나 환경변수를 쓴다.

사용:
  python3 flingbiz_daily.py --input es_input.json [--dry-run]
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta, date

# Windows에서 stdout이 콘솔이 아니면(파이프·리다이렉트·Claude Code 실행) 로케일 cp949가
# 적용돼 이모지 출력에서 UnicodeEncodeError로 죽는다. 여기서 UTF-8로 고정한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
KST = timezone(timedelta(hours=9))
API_BASE = "https://apis.pluglink.kr/v101"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ── 자격증명 (환경변수 우선, 없으면 기존 config 읽기 전용 재사용) ──────────
def creds():
    cfg = {}
    p = os.path.join(HERE, "ticket_config.json")
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

# ── 시각 정규화 (ES=UTC naive, REST=KST naive) ─────────────────────────────
def es_utc_to_kst(s):
    """ES의 'YYYY-MM-DD HH:MM:SS'(UTC) → KST datetime."""
    if not s:
        return None
    try:
        dt = datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(KST)

def rest_kst(s):
    """커넥트 REST의 'YYYY-MM-DD HH:MM:SS'(이미 KST) → KST datetime."""
    if not s:
        return None
    try:
        dt = datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=KST)

# ── Slack ────────────────────────────────────────────────────────────────
def slack_post(token, channel, blocks, text, dry):
    if dry:
        print(f"  [DRY-RUN] slack chat.postMessage → {channel}")
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
        print(f"  [ERROR] Slack 발송 실패: {res.get('error')}")
        return None
    return res.get("ts")

# ── 본 계산 ──────────────────────────────────────────────────────────────
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

    # 2) VOC 접수일 조회 (미완료 건만) → 경과일(달력일) 계산
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

    # 3) 전일 변화
    def by_owner_count(rows):
        # parentVocId 필터는 ES 쿼리(exists parentVocId)에서 이미 적용된다.
        # 전일 변화분은 충전소별 집계 형태({"targetStationId": X, "count": N})도 허용.
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

    # 라벨: 스케줄러가 조회 구간을 명시적으로 넘기면 그대로 쓴다(월요일 실행 시 주말 포함 구간).
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

    # 안전장치: 입력이 비정상이면 발송하지 않는다
    owners = data.get("owners") or {}
    if not owners or sum(len(v) for v in owners.values()) == 0:
        print("[ERROR] owners(소유주→충전소) 매핑이 비어 있음 — 오발송 방지로 중단")
        sys.exit(1)
    # 안전장치 2: ES 쿼리에 실제로 쓴 기준이 config와 다르면 중단
    qo = data.get("query_owners")
    if qo is not None and sorted(qo) != sorted(cfg["asset_owners"]):
        print("[ERROR] ES 조회에 쓴 소유주가 config와 다름 — 게시 중단")
        print(f"        조회: {sorted(qo)}")
        print("        config: " + str(sorted(cfg["asset_owners"])))
        sys.exit(1)
    qs = data.get("query_completed_statuses")
    if qs is not None and sorted(qs) != sorted(cfg["completed_statuses"]):
        print("[ERROR] ES 조회에 쓴 종결상태가 config와 다름 — 게시 중단")
        print(f"        조회: {sorted(qs)}")
        sys.exit(1)
    if qo is None or qs is None:
        print("[WARN] es_input.json에 query_owners/query_completed_statuses가 없어 기준 대조를 건너뜁니다")

    missing = [o for o in cfg["asset_owners"] if o not in owners]
    if missing:
        print(f"[WARN] 설정에 있으나 입력에 없는 소유주: {missing}")

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
