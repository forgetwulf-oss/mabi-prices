# mabi-life.github.io
마비노기 경매장 공유 시세 피드. 10분마다 GitHub Actions가 `items.json`의 아이템을
`auction/list`(최저가·매물수) + `auction/history`(체결)로 조회해 `docs/prices.json`에 게시.
history는 ~1시간 창이라 `docs/history_roll.json`에 `auction_buy_id`로 쌓아 24h 근사(`trades24`/`volume24`).

URL: https://mabi-life.github.io/prices.json

형식: `{updated, hotMinVolume, prices: {이름: {min, count, trades, volume, trades24, volume24, t}}}`

- `count` = 조회 시점 매물 수량 (참고)
- `trades`/`volume` = 이번 history 창의 거래횟수/체결물량
- `trades24`/`volume24` = 롤링 24h 근사 (중복 제거). 수집 공백 시 누락 가능
- 🔥 HOT = `volume24`(없으면 `volume`) ≥ `hotMinVolume` (피드 p80 근사, 알바·물교 재료용)

앱: 알바 도우미 https://mabi-life.github.io/alba/ · 물교 도우미 https://mabi-life.github.io/barter/ · 던전 도우미 https://mabi-life.github.io/dungeon/
