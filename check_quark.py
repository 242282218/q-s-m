import asyncio
import os
import sys

# 添加后端目录到 PYTHONPATH
sys.path.insert(0, os.path.abspath("backend"))

from app.core.config import get_settings
from app.quark.core.transfer_client import QuarkTransferClient

async def main():
    settings = get_settings()
    if not settings.quark_cookie:
        print("未找到 quark_cookie")
        return

    cookie = settings.quark_cookie
    client = QuarkTransferClient(cookie)
    
    try:
        # 获取目标目录fid
        path = "/收藏TV/动漫"
        fid = await client.get_fid_by_path(path)
        print(f"Directory fid for {path}: {fid}")
        
        if not fid:
            print("未能获取目标目录的 fid。")
            return
            
        res = await client.ls_dir(fid)
        
        if not res or not isinstance(res, dict):
            print("获取目录列表失败：响应异常。")
            return
            
        items = res.get("data", {}).get("list", [])
        
        for item in items:
            name = item.get("file_name") or item.get("name")
            
            if not name:
                continue
                
            is_dir = "DIR" if item.get("dir") else "FILE"
            print(f"[{is_dir}] {name} (fid: {item.get('fid')})")
            
            if "高木" in name:
                sub_fid = item.get("fid")
                print(f"  Fetching contents of {name}...")
                
                sub_res = await client.ls_dir(sub_fid)
                if sub_res and isinstance(sub_res, dict):
                    sub_items = sub_res.get("data", {}).get("list", [])
                    for sub_item in sub_items:
                        sub_name = sub_item.get("file_name") or sub_item.get("name")
                        sub_is_dir = "DIR" if sub_item.get("dir") else "FILE"
                        if sub_name:
                            print(f"    - [{sub_is_dir}] {sub_name}")

    except Exception as e:
        print(f"执行时捕获到异常: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
