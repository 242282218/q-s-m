"""
Quark 网盘路径解析工具。
提供“不创建目录”的路径->FID 查询，并带有前缀与目录列表缓存。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .transfer_client import QuarkTransferClient


class QuarkPathResolver:
    """按路径查找 Quark 目录 FID（只读，不创建目录）。"""

    def __init__(self, client: QuarkTransferClient):
        self.client = client
        self._path_cache: Dict[str, Optional[str]] = {"": "0", "/": "0"}
        self._ls_cache: Dict[str, Optional[List[dict]]] = {}

    @staticmethod
    def normalize_path(path: str) -> str:
        normalized = (path or "").strip().replace("\\", "/")
        if not normalized:
            return "/"
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        parts = [part for part in normalized.split("/") if part]
        return "/" + "/".join(parts) if parts else "/"

    async def list_dir(self, pdir_fid: str, *, use_cache: bool = True) -> Optional[List[dict]]:
        key = str(pdir_fid or "0")
        if use_cache and key in self._ls_cache:
            return self._ls_cache[key]

        response = await self.client.ls_dir(key)
        if response.get("code") != 0:
            if use_cache:
                self._ls_cache[key] = None
            return None

        items = response.get("data", {}).get("list", []) or []
        if use_cache:
            self._ls_cache[key] = items
        return items

    async def find_fid_by_path_no_create(self, path: str) -> Optional[str]:
        normalized = self.normalize_path(path)
        if normalized in self._path_cache:
            return self._path_cache[normalized]

        parts = [part for part in normalized.split("/") if part]
        current_path = ""
        current_fid = "0"

        for part in parts:
            current_path = f"{current_path}/{part}"
            if current_path in self._path_cache:
                cached = self._path_cache[current_path]
                if not cached:
                    self._path_cache[normalized] = None
                    return None
                current_fid = cached
                continue

            children = await self.list_dir(current_fid, use_cache=True)
            if children is None:
                self._path_cache[current_path] = None
                self._path_cache[normalized] = None
                return None

            next_fid: Optional[str] = None
            for item in children:
                name = item.get("file_name") or item.get("name")
                is_dir = (item.get("dir") is True) or (item.get("dir") == 1)
                if name == part and is_dir:
                    fid = item.get("fid")
                    next_fid = str(fid) if fid is not None else None
                    break

            self._path_cache[current_path] = next_fid
            if not next_fid:
                self._path_cache[normalized] = None
                return None
            current_fid = next_fid

        self._path_cache[normalized] = current_fid
        return current_fid
