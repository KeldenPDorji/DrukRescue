# Weather service (scaffold, task **D2**)

Current conditions per district, so the command centre can see heavy rain (flood/landslide risk).
Data comes from [Open-Meteo](https://open-meteo.com/), which is free and needs no API key, and is cached in Redis.

## Endpoints (gateway: `/api/weather/...`)

| Method | Path | Who | Behaviour |
|---|---|---|---|
| GET | `/weather` | any user | supported districts (done) |
| GET | `/weather/{district}` | any user | current weather; 404 for an unknown district; 502 if Open-Meteo fails and nothing is cached |

Example upstream call:

```
GET https://api.open-meteo.com/v1/forecast?latitude=27.47&longitude=89.64
    &current=temperature_2m,precipitation,rain,wind_speed_10m,weather_code
    &daily=precipitation_sum&timezone=Asia/Thimphu&forecast_days=1
```

## Implementation notes

- Use `httpx.Client(timeout=5)`. The call shows up in traces automatically.
- Redis: `redis.Redis.from_url(get_settings().redis_url)`, key `weather:<district>`, TTL `WEATHER_CACHE_SECONDS` (default 600).
- If Redis is down, still answer (just uncached). Log a warning.
- Add `redis` to `readiness_checks` in `create_app` only if you decide weather can't work without it (it can).
- The Helm chart already sets `redis.enabled: true`, so `REDIS_HOST`/`REDIS_PASSWORD` are injected.

## Done when

- [ ] `districts.py` lists all 20 dzongkhags
- [ ] Endpoint works with caching; tests mock Open-Meteo (`httpx.MockTransport`) and cover cache hit, miss and Redis down
- [ ] Optional: a `drukrescue_weather_precipitation_mm{district}` gauge for the dashboard
