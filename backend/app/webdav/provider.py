"""
夸克网盘 WebDAV Provider
将夸克网盘映射为 WebDAV 虚拟文件系统
"""
import io
import time
from typing import Optional, List, Dict, Any
from datetime import datetime

from wsgidav.dav_provider import DAVProvider, DAVCollection, DAVNonCollection
from wsgidav import util

from ..transfer.quark_client import QuarkTransferClient


class QuarkDAVProvider(DAVProvider):
    """
    夸克网盘 WebDAV Provider
    
    将夸克网盘目录结构映射为 WebDAV 虚拟文件系统
    """
    
    def __init__(self, cookie: str = ""):
        super().__init__()
        self.cookie = cookie
        # 目录缓存: path -> (files, timestamp)
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = 60  # 缓存 60 秒
        # fid 缓存: path -> fid
        self._fid_cache: Dict[str, str] = {"/": "0"}

    def _get_client(self) -> QuarkTransferClient:
        """获取夸克客户端"""
        return QuarkTransferClient(self.cookie)

    def get_resource_inst(self, path: str, environ: dict) -> Optional["DAVProvider"]:
        """根据路径返回资源实例"""
        path = path.rstrip("/") or "/"
        
        # 根目录
        if path == "/":
            return QuarkRootCollection(path, environ, self)
        
        # 分解路径
        parent_path = "/".join(path.rsplit("/", 1)[:-1]) or "/"
        name = path.rsplit("/", 1)[-1]
        
        # 获取父目录
        parent = self._get_dir_info(parent_path, environ)
        if not parent:
            return None
        
        # 在父目录中查找
        for item in parent:
            if item.get("file_name") == name:
                if item.get("dir"):
                    return QuarkCollection(path, environ, self, item)
                else:
                    return QuarkFile(path, environ, self, item)
        
        return None

    def _get_dir_info(self, path: str, environ: dict) -> Optional[List[Dict]]:
        """获取目录内容（带缓存）"""
        # 检查缓存
        if path in self._cache:
            files, timestamp = self._cache[path]
            if time.time() - timestamp < self._cache_ttl:
                return files
        
        # 获取目录 fid
        fid = self._get_fid(path, environ)
        if not fid:
            return None
        
        # 调用 API 获取目录内容
        import asyncio
        
        async def fetch():
            client = self._get_client()
            try:
                response = await client.ls_dir(fid)
                if response.get("code") == 0:
                    return response.get("data", {}).get("list", [])
                return None
            finally:
                await client.close()
        
        try:
            files = asyncio.run(fetch())
        except Exception as e:
            print(f"DEBUG: Error in _get_dir_info: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            raise e
        
        if files is not None:
            self._cache[path] = (files, time.time())
            # 更新 fid 缓存
            for item in files:
                item_path = f"{path}/{item['file_name']}".replace("//", "/")
                self._fid_cache[item_path] = item["fid"]
        
        return files

    def _get_fid(self, path: str, environ: dict) -> Optional[str]:
        """获取路径对应的 fid"""
        if path in self._fid_cache:
            return self._fid_cache[path]
        
        # 需要遍历父目录来获取
        parts = [p for p in path.split("/") if p]
        current_path = "/"
        current_fid = "0"
        
        for part in parts:
            files = self._get_dir_info(current_path, environ)
            if not files:
                return None
            
            found = False
            for item in files:
                if item.get("file_name") == part:
                    current_fid = item["fid"]
                    current_path = f"{current_path}/{part}".replace("//", "/")
                    self._fid_cache[current_path] = current_fid
                    found = True
                    break
            
            if not found:
                return None
        
        return current_fid


class QuarkRootCollection(DAVCollection):
    """根目录"""
    
    def __init__(self, path: str, environ: dict, provider: QuarkDAVProvider):
        super().__init__(path, environ)
        self.provider = provider

    def get_display_info(self) -> dict:
        return {"type": "Directory"}

    def get_member_names(self) -> List[str]:
        """返回子目录/文件名列表"""
        files = self.provider._get_dir_info("/", self.environ)
        if files:
            return [f["file_name"] for f in files]
        return []

    def get_member(self, name: str) -> Optional["DAVProvider"]:
        """获取子目录/文件"""
        path = f"/{name}"
        return self.provider.get_resource_inst(path, self.environ)

    def get_creation_date(self) -> float:
        return time.time()

    def get_last_modified(self) -> float:
        return time.time()


class QuarkCollection(DAVCollection):
    """夸克目录"""
    
    def __init__(self, path: str, environ: dict, provider: QuarkDAVProvider, info: Dict):
        super().__init__(path, environ)
        self.provider = provider
        self.info = info

    def get_display_info(self) -> dict:
        return {"type": "Directory"}

    def get_member_names(self) -> List[str]:
        """返回子目录/文件名列表"""
        files = self.provider._get_dir_info(self.path, self.environ)
        if files:
            return [f["file_name"] for f in files]
        return []

    def get_member(self, name: str) -> Optional["DAVProvider"]:
        """获取子目录/文件"""
        path = f"{self.path}/{name}".replace("//", "/")
        return self.provider.get_resource_inst(path, self.environ)

    def get_creation_date(self) -> float:
        updated_at = self.info.get("updated_at")
        if updated_at:
            return updated_at / 1000
        return time.time()

    def get_last_modified(self) -> float:
        updated_at = self.info.get("updated_at")
        if updated_at:
            return updated_at / 1000
        return time.time()


class QuarkFile(DAVNonCollection):
    """夸克文件"""
    
    def __init__(self, path: str, environ: dict, provider: QuarkDAVProvider, info: Dict):
        super().__init__(path, environ)
        self.provider = provider
        self.info = info
        self._download_url: Optional[str] = None

    def get_display_info(self) -> dict:
        return {"type": "File"}

    def get_content_length(self) -> int:
        return self.info.get("size", 0)

    def get_content_type(self) -> str:
        # 根据扩展名判断
        name = self.info.get("file_name", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        
        mime_types = {
            "mp4": "video/mp4",
            "mkv": "video/x-matroska",
            "avi": "video/x-msvideo",
            "mov": "video/quicktime",
            "wmv": "video/x-ms-wmv",
            "flv": "video/x-flv",
            "webm": "video/webm",
            "mp3": "audio/mpeg",
            "flac": "audio/flac",
            "wav": "audio/wav",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "gif": "image/gif",
            "txt": "text/plain",
            "srt": "text/plain",
            "ass": "text/plain",
        }
        
        return mime_types.get(ext, "application/octet-stream")

    def get_creation_date(self) -> float:
        updated_at = self.info.get("updated_at")
        if updated_at:
            return updated_at / 1000
        return time.time()

    def get_last_modified(self) -> float:
        updated_at = self.info.get("updated_at")
        if updated_at:
            return updated_at / 1000
        return time.time()

    def support_ranges(self) -> bool:
        return True

    def get_etag(self):
        """Return generic etag"""
        fid = self.info.get("fid", "")
        updated_at = self.info.get("updated_at", 0)
        return f"{fid}-{updated_at}"

    def support_etag(self):
        """Return True if class supports get_etag()."""
        return True

    def get_content(self) -> io.IOBase:
        """
        获取文件内容流
        
        这里返回一个代理流，实际使用时会重定向到夸克的下载链接
        """
        # 获取下载链接
        if not self._download_url:
            self._download_url = self._get_download_url()
        
        if self._download_url:
            # 返回一个流式代理
            return QuarkFileStream(self._download_url, self.info.get("size", 0))
        
        return io.BytesIO(b"")

    def _get_download_url(self) -> Optional[str]:
        """获取文件下载链接"""
        import asyncio
        import sys
        
        try:
            async def fetch():
                client = self.provider._get_client()
                try:
                    fid = self.info.get("fid")
                    if not fid:
                        return None
                    
                    # 调用下载接口获取直链
                    url = f"{client.BASE_URL}/1/clouddrive/file/download"
                    params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
                    payload = {"fids": [fid]}
                    
                    response = await client._send_request("POST", url, params=params, json=payload)
                    
                    if response.get("code") == 0:
                        data = response.get("data", [])
                        if data and len(data) > 0:
                            return data[0].get("download_url")
                    
                    return None
                finally:
                    await client.close()
            
            return asyncio.run(fetch())
        except Exception as e:
            print(f"DEBUG: Error in _get_download_url: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            raise e


class QuarkFileStream(io.IOBase):
    """夸克文件流代理"""
    
    def __init__(self, url: str, size: int):
        self.url = url
        self.size = size
        self._response = None
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:  # SEEK_SET
            self._position = offset
        elif whence == 1:  # SEEK_CUR
            self._position += offset
        elif whence == 2:  # SEEK_END
            self._position = self.size + offset
        return self._position

    def read(self, size: int = -1) -> bytes:
        import httpx
        
        headers = {}
        if self._position > 0 or (size > 0 and size < self.size):
            end = self._position + size - 1 if size > 0 else ""
            headers["Range"] = f"bytes={self._position}-{end}"
        
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                response = client.get(self.url, headers=headers)
                data = response.content
                self._position += len(data)
                return data
        except Exception:
            return b""

    def close(self):
        pass
