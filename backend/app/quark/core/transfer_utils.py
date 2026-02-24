"""
夸克转存工具函数
"""
import asyncio
import random
import time
from typing import Optional


def generate_timestamp() -> str:
    """
    生成时间戳
    """
    return str(int(time.time()))


def generate_random_dt() -> str:
    """
    生成随机dt参数
    """
    return str(random.randint(10000000, 99999999)) + generate_timestamp()


def parse_share_url(url: str) -> Optional[str]:
    """
    解析分享链接，提取pwd_id
    
    Args:
        url: 分享链接
        
    Returns:
        pwd_id，失败返回None
    """
    if "pan.quark.cn/s/" in url:
        # 格式：https://pan.quark.cn/s/xxx
        parts = url.split("/s/")
        if len(parts) > 1:
            pwd_id = parts[1].split("?")[0]
            return pwd_id
    elif "pan.quark.cn/share/" in url:
        # 格式：https://pan.quark.cn/share/xxx
        parts = url.split("/share/")
        if len(parts) > 1:
            pwd_id = parts[1].split("?")[0]
            return pwd_id
    return None


async def random_delay(min_delay: float = 0.5, max_delay: float = 1.5) -> None:
    """
    随机延迟，避免请求过于频繁
    
    Args:
        min_delay: 最小延迟时间（秒）
        max_delay: 最大延迟时间（秒）
    """
    await asyncio.sleep(random.uniform(min_delay, max_delay))
