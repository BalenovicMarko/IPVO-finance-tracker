# Finance Tracker - Phase 3 (Fixed)

Covers Phase 1 + Phase 2 + Phase 3.

## Phase 3
- **Streaming:** API publishes `transaction_created` events to Redpanda (Kafka API) topic `transactions`.
- **Alert consumer:** `alert-service` consumes events, keeps baseline stats per user+category in Redis (mean/std),
  and writes alerts to Mongo (`alerts` collection).
- **Cache evaluation:** `/monthly_summary` optionally caches monthly aggregates in Redis (TTL=60s) so you can compare
  `useCache=true` vs `useCache=false`.

## Run
```powershell
docker compose down -v
docker compose up --build
```

## GUI demo
Swagger:
- http://localhost:8080/docs

### Alerts demo
1) POST /users -> copy id
2) POST /transactions (x8) in category Food amount ~500
3) POST /transactions (x1) in category Food amount 20000
4) GET /alerts?userId=...

### Cache demo
- GET /monthly_summary?userId=...&year=2026&month=1&useCache=true
- call again (cached)
- compare with useCache=false
