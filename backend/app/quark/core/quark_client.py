import asyncio
import re
import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Set, Any, Tuple

import aiohttp

from app.core.config import get_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@dataclass
class QuarkResource:
    id: int
    name: str
    link: str
    size: str
    updatetime: str
    categoryid: int = 0
    uploaderid: str = ""
    views: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


class AsyncQuarkAPIClient:
    """
    夸克资源搜索客户端，用于与夸克搜索API交互
    修复了API基础URL、请求格式和链接验证逻辑
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        max_retries: Optional[int] = None,
        retry_delay: float = 1.0,
        rate_limit: Optional[float] = None,
        timeout: Optional[int] = None,
    ):
        settings = get_settings()
        base_url = base_url or settings.quark_search_base_url
        max_retries = max_retries or settings.quark_search_max_retries
        rate_limit = rate_limit if rate_limit is not None else settings.quark_search_rate_limit
        timeout = timeout or settings.quark_search_timeout
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.last_request_time = 0.0
        self.seen_ids: Set[int] = set()
        self._session: Optional[aiohttp.ClientSession] = None

        self.headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        }

    @property
    def session(self) -> aiohttp.ClientSession:
        """延迟创建并复用 session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers=self.headers
            )
        return self._session

    async def close(self) -> None:
        """关闭客户端会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "AsyncQuarkAPIClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def _rate_limit_wait(self):
        now = time.time()
        delta = now - self.last_request_time
        if delta < self.rate_limit:
            await asyncio.sleep(self.rate_limit - delta)
        self.last_request_time = time.time()

    async def _get(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        await self._rate_limit_wait()
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    try:
                        error_data = await resp.json()
                        logger.warning(f"夸克搜索 API HTTP {resp.status}: {error_data}")
                    except Exception as parse_err:
                        text = await resp.text()
                        logger.warning(f"夸克搜索 API HTTP {resp.status}: {text[:200]}, 解析错误: {parse_err}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
            except Exception as e:
                logger.warning(f"夸克搜索请求异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        return None

    async def _post(self, url: str, data: Optional[Dict] = None) -> Optional[Dict]:
        await self._rate_limit_wait()
        for attempt in range(self.max_retries):
            try:
                async with self.session.post(url, json=data) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status != 200:
                        try:
                            error_data = await resp.json()
                            logger.warning(f"夸克搜索 API HTTP {resp.status}: {error_data}")
                        except Exception as parse_err:
                            text = await resp.text()
                            logger.warning(f"夸克搜索 API HTTP {resp.status}: {text[:200]}, 解析错误: {parse_err}")
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
            except Exception as e:
                logger.warning(f"夸克搜索请求异常 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        return None

    @staticmethod
    def _safe_text(value: Any, default: str = "") -> str:
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)

    def _parse_resource(self, raw: Dict) -> Optional[QuarkResource]:
        if not isinstance(raw, dict):
            return None
        try:
            link = self._safe_text(raw.get("url") or raw.get("link"))
            if not link or "pan.quark.cn" not in link:
                return None

            name = self._safe_text(raw.get("title") or raw.get("filename") or raw.get("note"), "未知资源")
            name = re.sub(r'<[^>]+>', '', name)
            name = re.sub(r'\s+', ' ', name).strip() or "未知资源"

            resource_id = self._safe_positive_int(raw.get("id")) or 0
            uploaderid = self._safe_text(raw.get("uploaderid") or raw.get("source"))

            return QuarkResource(
                id=resource_id,
                name=name,
                link=link,
                size=self._safe_text(raw.get("size")),
                updatetime=self._safe_text(raw.get("updatetime") or raw.get("datetime")),
                categoryid=self._safe_positive_int(raw.get("categoryid")) or 0,
                uploaderid=uploaderid,
                views=self._safe_positive_int(raw.get("views")) or 0,
            )
        except Exception as e:
            logger.warning(f"资源解析失败: {e}, raw_id={raw.get('id')}, link={link[:50] if 'link' in locals() else 'N/A'}")
            return None

    @staticmethod
    def _extract_quark_links_from_results(results: Any) -> List[Dict]:
        if not isinstance(results, list):
            return []

        resources: List[Dict] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            links = result.get("links")
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, dict) or link.get("type") != "quark":
                    continue
                url = link.get("url")
                if not isinstance(url, str) or "pan.quark.cn" not in url:
                    continue
                resources.append({
                    "url": url,
                    "title": result.get("title"),
                    "datetime": result.get("datetime"),
                    "source": result.get("source"),
                    "unique_id": result.get("unique_id"),
                })
        return resources

    @staticmethod
    def _extract_pansou_resources(data: Any) -> List[Dict]:
        if isinstance(data, list):
            return data
        if not isinstance(data, dict):
            return []

        resource_list = data.get("list")
        if isinstance(resource_list, list) and resource_list:
            return resource_list

        merged_by_type = data.get("merged_by_type")
        if isinstance(merged_by_type, dict):
            quark_resources = merged_by_type.get("quark")
            if isinstance(quark_resources, list):
                return quark_resources

        return AsyncQuarkAPIClient._extract_quark_links_from_results(data.get("results"))

    async def search_resources(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 100,
        deduplicate: bool = True,
    ) -> List[QuarkResource]:
        url = f"{self.base_url}/api/search"
        params = {
            "kw": keyword,
            "cloud_types": "quark",
            "page": page,
            "res": page_size,
        }
        resp = await self._get(url, params)
        if not resp:
            logger.warning(f"夸克搜索 API 调用失败: 未收到响应 (关键词: {keyword})")
            return []
        if resp.get("code") not in (0, 200):
            logger.warning(f"夸克搜索 API 错误: code={resp.get('code')}, message={resp.get('message', '未知错误')}, 关键词: {keyword}")
            return []
        raw_list = self._extract_pansou_resources(resp.get("data"))
        if not raw_list:
            logger.info(f"夸克搜索 API 返回空列表 (关键词: {keyword})")
            return []

        logger.info(f"夸克搜索找到 {len(raw_list)} 个原始资源 (关键词: {keyword})")
        resources: List[QuarkResource] = []
        parsed_count = 0
        for r in raw_list:
            parsed = self._parse_resource(r)
            if parsed:
                resources.append(parsed)
                parsed_count += 1

        if parsed_count == 0 and len(raw_list) > 0:
            logger.warning(f"所有 {len(raw_list)} 个资源解析失败 (关键词: {keyword})")
        elif parsed_count < len(raw_list):
            logger.info(f"解析成功: {parsed_count}/{len(raw_list)} (关键词: {keyword})")
        if deduplicate:
            unique: Dict[Tuple[str, Any], QuarkResource] = {}
            for r in resources:
                normalized_id = self._safe_positive_int(r.id)
                if normalized_id is not None:
                    dedup_key: Tuple[str, Any] = ("id", normalized_id)
                else:
                    dedup_key = ("resource", self._resource_fingerprint(r))
                if dedup_key not in unique:
                    unique[dedup_key] = r
            resources = list(unique.values())
        return resources

    @staticmethod
    def _safe_positive_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _resource_fingerprint(resource: QuarkResource) -> Tuple[Any, ...]:
        return (
            resource.name,
            resource.link,
            resource.size,
            resource.updatetime,
            resource.categoryid,
            resource.uploaderid,
            resource.views,
        )
