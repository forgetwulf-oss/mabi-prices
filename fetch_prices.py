#!/usr/bin/env python3
"""마비노기 경매장 공유 시세 피드 생성기 (표준 라이브러리만 사용).
items.json의 모든 아이템 이름에 대해 Nexon Open API로 최저 단가를 조회해 docs/prices.json에 저장.
키는 환경변수 NEXON_API_KEY에서만 읽음. 조회 실패 시 이전 값을 유지."""
import json, os, sys, time, datetime, urllib.request, urllib.parse, urllib.error
H = os.path.dirname(os.path.abspath(__file__))
KEY = os.environ.get('NEXON_API_KEY') or sys.exit('NEXON_API_KEY 환경변수가 필요합니다')
GAP = float(os.environ.get('GAP', '0.6'))
KST = datetime.timezone(datetime.timedelta(hours=9))
now = lambda: datetime.datetime.now(KST).isoformat(timespec='seconds')
items = json.load(open(f'{H}/items.json', encoding='utf-8'))
names = sorted({n for v in items.values() for n in v})
out_p = f'{H}/docs/prices.json'
try: old = json.load(open(out_p, encoding='utf-8')).get('prices', {})
except Exception: old = {}

def get(name):
    u = 'https://open.api.nexon.com/mabinogi/v1/auction/list?item_name=' + urllib.parse.quote(name)
    for a in range(6):
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={'x-nxopen-api-key': KEY}), timeout=25)
            return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(min(60, 3 * 2 ** a)); continue
            if e.code == 400: return {'auction_item': []}
            raise
        except Exception:
            time.sleep(3 * (a + 1))
    raise RuntimeError('retries exhausted')

prices, ok, fail, empty = {}, 0, 0, 0
for i, n in enumerate(names):
    try:
        its = [x for x in get(n).get('auction_item', []) if x.get('item_name') == n and x.get('auction_price_per_unit')]
        if its:
            prices[n] = {'min': min(x['auction_price_per_unit'] for x in its), 'count': sum(x.get('item_count', 1) for x in its), 't': now()}
            ok += 1
        else:
            empty += 1
            if n in old: prices[n] = old[n]
    except Exception as e:
        fail += 1
        print(f'fail {n}: {type(e).__name__} {getattr(e, "code", "")}', file=sys.stderr)
        if n in old: prices[n] = old[n]
    print(f'[{i+1}/{len(names)}] {n}: {prices.get(n, {}).get("min")}')
    time.sleep(GAP)

if ok == 0 and old:
    print('no successful fetch; leaving file unchanged'); sys.exit(0)
os.makedirs(f'{H}/docs', exist_ok=True)
json.dump({'updated': now(), 'source': 'Nexon Open API auction/list (최저 단가)', 'prices': prices},
          open(out_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, sort_keys=True)
print(f'ok {ok} empty {empty} fail {fail} total {len(names)} stored {len(prices)}')
