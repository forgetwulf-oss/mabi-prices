# mabi-prices
마비노기 경매장 공유 시세 피드. 3시간마다 GitHub Actions가 `items.json`의 아이템 최저 단가를 조회해 `docs/prices.json`에 게시.

URL: https://forgetwulf-oss.github.io/mabi-prices/prices.json

형식: `{updated, prices: {이름: {min, count, t}}}`
