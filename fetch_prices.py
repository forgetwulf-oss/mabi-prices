#!/usr/bin/env python3
"""마비노기 경매장 공유 시세 피드 생성기 (표준 라이브러리만 사용).

items.json의 모든 아이템에 대해:
  - auction/list → 최저 단가(min), 매물 수량(count), 시각(t)
  - auction/history → 이번 조회 창의 거래횟수(trades), 체결물량(volume)

공식 history는 대략 최근 1시간만 제공됨. 10분마다 돌면서 auction_buy_id로
중복을 제거해 docs/history_roll.json에 쌓고, 24시간 창의 trades24/volume24를
prices.json에 같이 넣는다.

한계(의도적 근사):
  - 워커가 멈추거나 주기가 1시간을 넘기면 그 사이 체결은 유실될 수 있음
  - 부분일치로 섞인 동명/유사명은 item_name 정확 일치로 걸러 냄
  - 24h는 '수집된 고유 체결'이지 넥슨이 보장하는 공식 일일 통계가 아님
  - HOT 임계값(hotMinVolume)은 이번 피드 volume24의 대략 p80 (재료 알바/물교용)

키는 환경변수 NEXON_API_KEY에서만 읽음(로그에 키를 찍지 않음).
list 성공·history 실패 시 min/count는 유지하고 trades/volume만 비움(HOT off).
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error
H = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get('NEXON_API_KEY') or sys.exit('NEXON_API_KEY 환경변수가 필요합니다')
GAP = float(os.environ.get('GAP', '0.1'))
KST = datetime.timezone(datetime.timedelta(hours=9))
now = lambda: datetime.datetime.now(KST).isoformat(timespec='seconds')
UTC = datetime.timezone.utc
ROLL_HOURS = 24
items = json.load(open(f'{H}/items.json', encoding='utf-8'))
names = sorted({n for k, v in items.items() if not k.startswith('_') for n in v})
out_p = f'{H}/docs/prices.json'
roll_p = f'{H}/docs/history_roll.json'
try: old = json.load(open(out_p, encoding='utf-8')).get('prices', {})
except Exception: old = {}
try: roll = json.load(open(roll_p, encoding='utf-8'))
except Exception: roll = {}
if not isinstance(roll.get('items'), dict):
    roll = {'items': {}}

def api_get(path_q):
    u = 'https://open.api.nexon.com/mabinogi/v1/' + path_q
    for a in range(4):
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(u, headers={'x-nxopen-api-key': KEY, 'accept': 'application/json'}),
                timeout=25)
            return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(min(30, 2 * 2 ** a)); continue
            if e.code == 400: return {}
            raise
        except Exception:
            time.sleep(3 * (a + 1))
    raise RuntimeError('retries exhausted')

def get_list(name):
    return api_get('auction/list?item_name=' + urllib.parse.quote(name))

def get_hist(name):
    return api_get('auction/history?item_name=' + urllib.parse.quote(name))

def parse_buy_ts(s):
    """Nexon date_auction_buy → aware UTC datetime, or None."""
    if not s: return None
    try:
        s = str(s).replace('Z', '+00:00')
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None

def fingerprint(row):
    """Stable id: prefer auction_buy_id, else time+price+count."""
    bid = row.get('auction_buy_id')
    if bid is not None and str(bid) != '':
        return str(bid)
    return '%s|%s|%s' % (
        row.get('date_auction_buy') or '',
        row.get('auction_price_per_unit') or '',
        row.get('item_count') or '')

def prune_and_merge(name, rows, now_utc):
    bucket = dict(roll['items'].get(name) or {})
    cutoff = now_utc - datetime.timedelta(hours=ROLL_HOURS)
    # drop stale
    keep = {}
    for k, v in bucket.items():
        ts = parse_buy_ts((v or {}).get('t'))
        if ts and ts >= cutoff:
            keep[k] = v
    for row in rows:
        fid = fingerprint(row)
        ts = parse_buy_ts(row.get('date_auction_buy')) or now_utc
        if ts < cutoff:
            continue
        n = int(row.get('item_count') or 1)
        # keep earliest-seen n if already present (same id)
        if fid not in keep:
            keep[fid] = {'t': ts.isoformat().replace('+00:00', 'Z'), 'n': n}
    roll['items'][name] = keep
    trades24 = len(keep)
    volume24 = sum(int((v or {}).get('n') or 0) for v in keep.values())
    return trades24, volume24

def pct(xs, p):
    if not xs: return None
    xs = sorted(xs)
    i = int(round((len(xs) - 1) * p / 100))
    return xs[max(0, min(len(xs) - 1, i))]

prices, ok, fail, empty, streak = {}, 0, 0, 0, 0
hist_ok, hist_fail = 0, 0
now_utc = datetime.datetime.now(UTC)

for i, n in enumerate(names):
    if streak >= 5:  # 일일 한도 소진 등: 남은 항목은 이전 값 유지하고 중단
        if n in old: prices[n] = old[n]
        continue
    entry = dict(old.get(n) or {})
    list_ok = False
    try:
        its = [x for x in (get_list(n).get('auction_item') or [])
               if x.get('item_name') == n and x.get('auction_price_per_unit')]
        if its:
            entry['min'] = min(x['auction_price_per_unit'] for x in its)
            entry['count'] = sum(x.get('item_count', 1) for x in its)
            entry['t'] = now()
            ok += 1; streak = 0; list_ok = True
        else:
            empty += 1; streak = 0
            # keep previous min/count if any
    except Exception as e:
        fail += 1; streak += 1
        print(f'fail list {n}: {type(e).__name__} {getattr(e, "code", "")}', file=sys.stderr)

    # history: independent; failure → no trades/volume (HOT off), keep min
    try:
        time.sleep(GAP)
        hist = [x for x in (get_hist(n).get('auction_history') or [])
                if x.get('item_name') == n]
        trades = len(hist)
        volume = sum(int(x.get('item_count') or 1) for x in hist)
        entry['trades'] = trades
        entry['volume'] = volume
        t24, v24 = prune_and_merge(n, hist, now_utc)
        entry['trades24'] = t24
        entry['volume24'] = v24
        hist_ok += 1
    except Exception as e:
        hist_fail += 1
        print(f'fail hist {n}: {type(e).__name__} {getattr(e, "code", "")}', file=sys.stderr)
        # drop stale window fields so HOT turns off; keep min/count/t
        for k in ('trades', 'volume'):
            entry.pop(k, None)
        # still prune old roll entries for this item (no new merges)
        if n in roll['items']:
            t24, v24 = prune_and_merge(n, [], now_utc)
            entry['trades24'] = t24
            entry['volume24'] = v24

    if entry.get('min') is not None or n in old:
        # ensure we don't store empty husks without min from nowhere
        if entry.get('min') is not None:
            prices[n] = entry
        elif n in old:
            prices[n] = old[n]

    print(f'[{i+1}/{len(names)}] {n}: min={prices.get(n, {}).get("min")} vol={prices.get(n, {}).get("volume")} vol24={prices.get(n, {}).get("volume24")}')
    time.sleep(GAP)

if ok == 0 and old:
    print('no successful fetch; leaving file unchanged'); sys.exit(0)

# HOT threshold: ~p80 of volume24 among items with any 24h activity (materials-oriented)
vols = [p['volume24'] for p in prices.values()
        if isinstance(p.get('volume24'), int) and p['volume24'] > 0]
hot_min = pct(vols, 80)
if hot_min is None:
    hot_min = 300
else:
    hot_min = max(50, int(hot_min))

os.makedirs(f'{H}/docs', exist_ok=True)
roll['updated'] = now()
json.dump(roll, open(roll_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, sort_keys=True)

payload = {
    'updated': now(),
    'source': 'Nexon Open API auction/list + auction/history (최저가·체결)',
    'hotMinVolume': hot_min,
    'hotNote': '🔥 = volume24(없으면 volume) ≥ hotMinVolume (이번 피드 p80 근사). count는 매물 수(참고용).',
    'prices': prices,
}
json.dump(payload, open(out_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, sort_keys=True)
print(f'ok {ok} empty {empty} fail {fail} hist_ok {hist_ok} hist_fail {hist_fail} '
      f'total {len(names)} stored {len(prices)} hotMinVolume {hot_min}')
