# API Contract (Step 2: Unified Envelope)

## Unified Response
All REST endpoints now return:

```json
{
  "code": 0,
  "message": "OK",
  "data": {}
}
```

- `code: number` (`0` = success, non-zero = business/error code)
- `message: string`
- `data: T`

## Unified Pagination
All paginated responses use:

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 0,
    "total_pages": 0
  }
}
```

Current paginated endpoint:
- `GET /api/collection/list`

## Time Format
- All time fields use ISO 8601 string format (`date-time`).
- Examples: `saved_at`, `timestamp`.

## Contract File
- Full JSON Schema/OpenAPI contract: [api-contract-step2-unified-openapi.json](/c:/Users/24228/Desktop/qsm/docs/api-contract-step2-unified-openapi.json)
- This file contains all `/api/*` paths and component schemas, including SSE envelope schema (`SseEnvelope`).

