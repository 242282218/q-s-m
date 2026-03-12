# QSM Frontend (Vue 3 + Vite)

## Run
```bash
pnpm install
pnpm dev
```

Default dev URL: `http://127.0.0.1:5173`  
API proxy target: `http://127.0.0.1:8000`

## Build
```bash
pnpm build
```

## Test
```bash
pnpm test
```

## Notes
- All API calls use the unified envelope: `code/message/data`.
- Pagination uses: `items + pagination(page, page_size, total, total_pages)`.
- SSE endpoints are parsed as `SseEnvelope`.
