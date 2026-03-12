import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.sse_stream import stream_with_heartbeat


class SseHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_with_heartbeat_emits_heartbeat_during_idle_gap(self):
        async def slow_source():
            await __import__("asyncio").sleep(0.03)
            yield "data: event\n\n"

        chunks = []
        async for chunk in stream_with_heartbeat(
            slow_source(),
            heartbeat_interval=0.005,
            heartbeat_message=": heartbeat\n\n",
        ):
            chunks.append(chunk)
            if len(chunks) == 2:
                break

        self.assertEqual(chunks[0], ": heartbeat\n\n")
        self.assertEqual(chunks[1], "data: event\n\n")


if __name__ == "__main__":
    unittest.main()
