"""
探测夸克分享链接的完整文件树结构 - 输出到文件
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.config import get_settings
from app.quark.core.transfer_client import QuarkTransferClient

lines = []

async def dump_share_tree(share_url: str, max_depth: int = 5):
    settings = get_settings()
    cookie = settings.quark_transfer_cookie or settings.quark_cookie
    client = QuarkTransferClient(cookie)

    try:
        is_valid, pwd_id, stoken = await client.validate_share_link(share_url)
        lines.append(f"链接有效: {is_valid}, pwd_id: {pwd_id}")

        if not is_valid or not pwd_id or not stoken:
            lines.append("链接无效")
            return

        async def walk(pdir_fid: str, depth: int, prefix: str):
            if depth > max_depth:
                lines.append(f"{prefix}... (depth limit)")
                return

            detail = await client.get_detail(pwd_id, stoken, pdir_fid)
            if detail.get("code") != 0:
                lines.append(f"{prefix}[ERROR] {detail.get('message')}")
                return

            items = detail.get("data", {}).get("list", []) or []
            for i, item in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                child_prefix = "    " if is_last else "│   "

                fid = item.get("fid", "")
                name = item.get("file_name", "")
                is_dir = item.get("dir", False)
                size = item.get("size", 0)

                if is_dir:
                    lines.append(f"{prefix}{connector}📁 {name}/")
                    await walk(fid, depth + 1, prefix + child_prefix)
                else:
                    size_mb = size / (1024 * 1024) if size else 0
                    lines.append(f"{prefix}{connector}📄 {name}  ({size_mb:.1f}MB)")

        lines.append(f"\n=== 分享文件树: {share_url} ===\n")
        await walk("0", 0, "")

    finally:
        await client.close()


if __name__ == "__main__":
    url = "https://pan.quark.cn/s/34f1bf1092e9"
    asyncio.run(dump_share_tree(url))
    
    output = "\n".join(lines)
    with open("share_tree_output.txt", "w", encoding="utf-8") as f:
        f.write(output)
    print(output)
