from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator

_STREAM_END = object()


async def stream_with_heartbeat(
    source: AsyncIterator[str],
    *,
    heartbeat_interval: float = 15.0,
    heartbeat_message: str = ": heartbeat\n\n",
) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[object] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for chunk in source:
                await queue.put(chunk)
        finally:
            await queue.put(_STREAM_END)

    producer = asyncio.create_task(produce())

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield heartbeat_message
                continue

            if chunk is _STREAM_END:
                break

            yield chunk  # type: ignore[misc]
    finally:
        if not producer.done():
            producer.cancel()
        await asyncio.gather(producer, return_exceptions=True)
