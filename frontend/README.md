# QSM Frontend (Vue 3 + Vite)

## Run
```bash
npm install
npm run dev
```

Default dev URL: `http://127.0.0.1:5173`  
API proxy target: `http://127.0.0.1:8000`

## Build
```bash
npm run build
```

## Notes
- All API calls use unified envelope: `code/message/data`.
- Pagination uses: `items + pagination(page, page_size, total, total_pages)`.
- SSE endpoints (`/api/transfer/rename`, `/api/collection/verify`) are parsed as `SseEnvelope`.

