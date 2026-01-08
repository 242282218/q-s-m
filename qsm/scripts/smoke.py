"""
简单冒烟测试：对已启动的本地服务发请求验证核心页面。
"""

import os
import sys
import anyio
import httpx

BASE = os.getenv("SMOKE_BASE_URL", "http://127.0.0.1:7777")


async def fetch_and_assert(path: str, keyword: str) -> None:
    url = f"{BASE}{path}"
    async with httpx.AsyncClient(timeout=12) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise SystemExit(f"FAIL {url} status={resp.status_code}")
    if keyword not in resp.text:
        raise SystemExit(f"FAIL {url} keyword '{keyword}' not found")
    print(f"OK   {url}")


async def main() -> None:
    await fetch_and_assert("/", "本周趋势")
    await fetch_and_assert("/search?q=Matrix", "Matrix")
    await fetch_and_assert("/movie/603", "评分")


if __name__ == "__main__":
    try:
        anyio.run(main)
    except SystemExit as exc:
        sys.exit(exc.code)
