# Health Data Hub API

HealthSave expects the server URL to be the base URL only, for example
`https://health.example.com`. The app appends the paths below.

If `API_KEY` is set on the server, protected endpoints require:

```http
x-api-key: your-api-key
```

## Health Checks

### `GET /health`

Returns a minimal process health response.

```json
{
  "status": "ok"
}
```

### `GET /api/health`

Returns the same app-friendly health response.

```json
{
  "status": "ok"
}
```

## Batch Ingest

### `POST /api/apple/batch`

Receives one HealthKit metric batch.

```json
{
  "metric": "heart_rate",
  "batch_index": 0,
  "total_batches": 1,
  "samples": [
    {
      "date": "2026-04-10T12:00:00Z",
      "qty": 72,
      "unit": "count/min",
      "source": "Apple Watch"
    }
  ]
}
```

Success response:

```json
{
  "status": "processed",
  "metric": "heart_rate",
  "batch": 0,
  "total_batches": 1,
  "records": 1
}
```

Empty batch response:

```json
{
  "status": "empty",
  "metric": "heart_rate",
  "batch": 0,
  "records": 0
}
```

### Dedicated Metrics

These metrics are stored in first-class tables:

| Metric | Table | Notes |
|--------|-------|-------|
| `heart_rate` | `heart_rate` | Beats per minute |
| `heart_rate_variability` | `hrv` | Stored as SDNN milliseconds |
| `blood_oxygen` | `blood_oxygen` | Accepts `97` or `0.97` |
| `oxygen_saturation` | `blood_oxygen` | Alias used by HealthSave |
| `body_temperature` | `body_temperature` | Celsius |
| `wrist_temperature` | `body_temperature` | Alias used by HealthSave |
| `sleep_analysis` | `sleep_sessions` | Aggregates sleep stage samples into sessions |
| `workouts` | `workouts` | Stores workout summaries |
| `activity_summaries` | `daily_activity` | Stores day-level activity summary payloads |

### Daily Activity Quantity Metrics

HealthSave can send these day-level totals as ordinary quantity batches.
The server maps them into `daily_activity` so Grafana dashboards populate
without requiring a separate `activity_summaries` payload.

| Metric | `daily_activity` column |
|--------|--------------------------|
| `step_count` | `steps` |
| `distance_walking_running` | `distance_m` |
| `distance_cycling` | `distance_m` |
| `distance_wheelchair` | `distance_m` |
| `flights_climbed` | `floors_climbed` |
| `active_energy_burned` | `active_calories` |
| `basal_energy_burned` | `total_calories` |
| `apple_exercise_time` | `active_minutes` |
| `apple_stand_time` | `stand_hours` |

All other metric names are accepted and stored in `quantity_samples` with:

```json
{
  "time": "sample date",
  "metric_name": "metric",
  "value": "qty",
  "unit": "unit",
  "source_id": "source"
}
```

## Sync Status

### `GET /api/apple/status`

Returns a flat JSON object. This shape is important: the HealthSave iOS app
reads each top-level value as a metric status object.

Correct response shape:

```json
{
  "heart_rate": {
    "count": 123,
    "oldest": "2026-04-01 08:00:00+00:00",
    "newest": "2026-04-10 12:00:00+00:00"
  },
  "hrv": {
    "count": 45,
    "oldest": "2026-04-01 08:00:00+00:00",
    "newest": "2026-04-10 12:00:00+00:00"
  },
  "blood_oxygen": {
    "count": 12,
    "oldest": "2026-04-02 09:00:00+00:00",
    "newest": "2026-04-09 21:00:00+00:00"
  },
  "daily_activity": {
    "count": 10,
    "oldest": "2026-04-01",
    "newest": "2026-04-10"
  },
  "sleep_sessions": {
    "count": 8,
    "oldest": "2026-04-02 23:10:00+00:00",
    "newest": "2026-04-10 06:45:00+00:00"
  },
  "workouts": {
    "count": 3,
    "oldest": "2026-04-03 17:30:00+00:00",
    "newest": "2026-04-08 18:15:00+00:00"
  },
  "quantity_samples": {
    "count": 900,
    "oldest": "2026-04-01 00:00:00+00:00",
    "newest": "2026-04-10 12:00:00+00:00"
  }
}
```

Do not wrap this endpoint as `{"status":"ok","counts":{...}}`; that shape is
not compatible with the current iOS status UI.

## Compatibility Notes

- Timestamp values should be ISO 8601 strings. A trailing `Z` is accepted.
- Date-only daily activity values can use `YYYY-MM-DD` or an ISO timestamp.
- Batch ingestion is idempotent for first-class time-series tables through
  `ON CONFLICT` upserts.
- Unknown metric names are intentionally accepted so new HealthKit types can
  be stored before they receive first-class dashboards.
