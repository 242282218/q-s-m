"""
夸克转存客户端
"""
import asyncio
import time
import random
import logging
import re
import warnings
from http.cookies import SimpleCookie
from yarl import URL
import aiohttp
from typing import List, Tuple, Optional, Dict, Any

from app.quark.core.transfer_models import FileDetail, TaskStatus

logger = logging.getLogger(__name__)


class QuarkTransferClient:
    """
    夸克转存客户端
    """

    BASE_URL = "https://drive-pc.quark.cn"
    BASE_URL_APP = "https://drive-m.quark.cn"
    
    def __init__(self, cookie: str):
        """
        初始化转存客户端
        
        Args:
            cookie: 夸克网盘Cookie
        """
        self.cookie = cookie
        self._session: Optional[aiohttp.ClientSession] = None
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 "
            "Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"
        )
        self.mparam = self._match_mparam_from_cookie(cookie)
        self._cookies_loaded = False

    @property
    def session(self) -> aiohttp.ClientSession:
        """延迟创建 session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._cookies_loaded = False
        if not self._cookies_loaded:
            self._load_cookies(self.cookie)
            self._cookies_loaded = True
        return self._session

    def _match_mparam_from_cookie(self, cookie: str) -> Dict[str, str]:
        if not cookie:
            return {}
        kps_match = re.search(r"(?<!\w)kps=([a-zA-Z0-9%+/=]+)[;&]?", cookie)
        sign_match = re.search(r"(?<!\w)sign=([a-zA-Z0-9%+/=]+)[;&]?", cookie)
        vcode_match = re.search(r"(?<!\w)vcode=([a-zA-Z0-9%+/=]+)[;&]?", cookie)
        if kps_match and sign_match and vcode_match:
            return {
                "kps": kps_match.group(1).replace("%25", "%"),
                "sign": sign_match.group(1).replace("%25", "%"),
                "vcode": vcode_match.group(1).replace("%25", "%"),
            }
        return {}

    def _load_cookies(self, cookie_str: str) -> None:
        if not cookie_str:
            return
        jar = SimpleCookie()
        jar.load(cookie_str)
        cookies = {key: morsel.value for key, morsel in jar.items()}
        if cookies and self._session:
            for base_url in ("https://pan.quark.cn", "https://drive-pc.quark.cn", "https://drive-m.quark.cn"):
                self._session.cookie_jar.update_cookies(cookies, response_url=URL(base_url))
        
    async def close(self) -> None:
        """关闭客户端会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "QuarkTransferClient":
        """异步上下文管理器进入"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器退出"""
        await self.close()

    def __del__(self):
        """析构时警告未关闭的 session"""
        if self._session and not self._session.closed:
            warnings.warn(
                f"{self.__class__.__name__} session not closed. "
                "Use 'async with' or call 'await close()' explicitly.",
                ResourceWarning,
                stacklevel=2
            )

    def _build_headers(self, json_body: bool = False, include_cookie: bool = True) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        if include_cookie and self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def _parse_json_response(self, response, operation: str) -> Optional[Dict[str, Any]]:
        """
        解析 JSON 响应的辅助方法。
        
        Args:
            response: aiohttp 响应对象
            operation: 操作名称（用于日志）
            
        Returns:
            解析后的 JSON 数据，失败返回 None
        """
        if response.status in (301, 302, 303, 307, 308):
            logger.error(f"{operation}被重定向: {response.headers.get('location')}")
            return None
        if response.status != 200:
            logger.error(f"{operation}失败，响应状态: {response.status}")
            return None
        if not (response.content_type and "json" in response.content_type):
            logger.error(f"{operation}返回非JSON: {response.content_type}")
            return None
        try:
            return await response.json()
        except Exception as e:
            logger.error(f"{operation} JSON解析失败: {e}")
            return None

    def _apply_mobile_share_params(self, url: str, params: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if not self.mparam:
            return url, params
        if self.BASE_URL in url:
            url = url.replace(self.BASE_URL, self.BASE_URL_APP)
            params.update(
                {
                    "device_model": "M2011K2C",
                    "entry": "default_clouddrive",
                    "_t_group": "0%3A_s_vp%3A1",
                    "dmn": "Mi%2B11",
                    "fr": "android",
                    "pf": "3300",
                    "bi": "35937",
                    "ve": "7.4.5.680",
                    "ss": "411x875",
                    "mi": "M2011K2C",
                    "nt": "5",
                    "nw": "0",
                    "kt": "4",
                    "pr": "ucpro",
                    "sv": "release",
                    "dt": "phone",
                    "data_from": "ucapi",
                    "kps": self.mparam.get("kps"),
                    "sign": self.mparam.get("sign"),
                    "vcode": self.mparam.get("vcode"),
                    "app": "clouddrive",
                    "kkkk": "1",
                }
            )
        return url, params
    
    async def get_stoken(self, pwd_id: str, passcode: str = "") -> Optional[str]:
        """
        获取分享的stoken
        
        Args:
            pwd_id: 分享ID
            passcode: 分享提取码（无提取码时为空字符串）
            
        Returns:
            stoken，失败返回None
        """
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/token"
        params = {"pr": "ucpro", "fr": "pc"}
        params["uc_param_str"] = ""
        url, params = self._apply_mobile_share_params(url, params)
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)
        payload = {"pwd_id": pwd_id, "passcode": passcode or ""}
        
        try:
            async with self.session.post(url, headers=headers, params=params, json=payload, allow_redirects=False) as response:
                data = await self._parse_json_response(response, "获取stoken")
                if data is None:
                    return None
                if data.get("data") and data["data"].get("stoken") and data.get("code") == 0:
                    return data["data"]["stoken"]
                logger.error(f"获取stoken失败: {data.get('message') or data.get('msg')}")
        except Exception as e:
            logger.error(f"获取stoken异常: {str(e)}")
        
        return None
    
    async def get_share_files(self, pwd_id: str, stoken: str, page: int = 1, pdir_fid: str = "0") -> Tuple[List[FileDetail], bool]:
        """
        获取分享文件列表
        
        Args:
            pwd_id: 分享ID
            stoken: 分享token
            page: 页码
            pdir_fid: 父目录ID
            
        Returns:
            (文件列表, 是否有下一页)
        """
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/detail"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": pdir_fid,
            "force": "0",
            "_page": page,
            "_size": "50",
            "_fetch_banner": "0",
            "_fetch_share": "0",
            "_fetch_total": "1",
            "_sort": "file_type:asc,updated_at:desc",
            "ver": "2",
        }
        params["uc_param_str"] = ""
        url, params = self._apply_mobile_share_params(url, params)
        headers = self._build_headers(include_cookie=not self.mparam)
        
        try:
            async with self.session.get(url, headers=headers, params=params, allow_redirects=False) as response:
                data = await self._parse_json_response(response, "获取分享文件")
                if data is None:
                    return [], False
                if data.get("code") == 0 and data.get("data") and data["data"].get("list"):
                    file_list = []
                    for item in data["data"]["list"]:
                        file_detail = FileDetail(
                            fid=item["fid"],
                            title=item.get("file_name") or item.get("name") or "",
                            file_type=2 if item.get("dir") else 1,
                            size=item.get("size", 0),
                            pdir_fid=item.get("pdir_fid", "0"),
                            share_fid_token=item.get("share_fid_token", "")
                        )
                        file_list.append(file_detail)
                    total = data.get("metadata", {}).get("_total", 0)
                    have_next = total > (page * int(params["_size"]))
                    return file_list, have_next
        except Exception as e:
            logger.error(f"获取分享文件异常: {str(e)}")
        
        return [], False
    
    async def save_files(self, fid_list: List[str], fid_token_list: List[str], to_pdir_fid: str, pwd_id: str, stoken: str) -> Optional[Dict[str, Any]]:
        """
        保存文件到网盘
        
        Args:
            fid_list: 文件ID列表
            fid_token_list: 文件token列表
            to_pdir_fid: 目标目录ID
            pwd_id: 分享ID
            stoken: 分享token
            
        Returns:
            保存结果，失败返回None
        """
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/save"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "app": "clouddrive",
            "__dt": int(random.uniform(1, 5) * 60 * 1000),
            "__t": time.time(),
        }
        url, params = self._apply_mobile_share_params(url, params)
        data = {
            "fid_list": fid_list,
            "fid_token_list": fid_token_list,
            "to_pdir_fid": to_pdir_fid,
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": "0",
            "scene": "link",
        }
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)
        
        try:
            async with self.session.post(url, headers=headers, params=params, json=data, allow_redirects=False) as response:
                result = await self._parse_json_response(response, "保存文件")
                if result is None:
                    return None
                if result.get("code") == 0 and result.get("data"):
                    return result["data"]
                logger.error(f"保存文件失败: {result.get('message') or result.get('msg')}")
        except Exception as e:
            logger.error(f"保存文件异常: {str(e)}")
        
        return None
    
    async def get_task_status(self, task_id: str, retry_index: int = 0) -> Optional[TaskStatus]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            retry_index: 重试索引
            
        Returns:
            任务状态，失败返回None
        """
        url = f"{self.BASE_URL}/1/clouddrive/task"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "task_id": task_id,
            "retry_index": retry_index,
            "__dt": int(random.uniform(1, 5) * 60 * 1000),
            "__t": time.time(),
        }
        headers = self._build_headers(include_cookie=not self.mparam)
        
        try:
            async with self.session.get(url, headers=headers, params=params, allow_redirects=False) as response:
                data = await self._parse_json_response(response, "获取任务状态")
                if data is None:
                    return None
                if data.get("code") == 0 and data.get("data"):
                    status_data = data["data"]
                    return TaskStatus(
                        task_id=task_id,
                        status=status_data.get("status", 0),
                        message=status_data.get("message") or status_data.get("task_title", ""),
                        progress=status_data.get("progress", 0)
                    )
        except Exception as e:
            logger.error(f"获取任务状态异常: {str(e)}")
        
        return None
    
    async def create_dir(self, dir_name: str, pdir_fid: str = "0") -> Optional[str]:
        """
        创建目录
        
        Args:
            dir_name: 目录名称
            pdir_fid: 父目录ID
            
        Returns:
            目录ID，失败返回None
        """
        url = f"{self.BASE_URL}/1/clouddrive/file"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        data = {
            "pdir_fid": pdir_fid,
            "file_name": dir_name,
            "dir_path": "",
            "dir_init_lock": False,
        }
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)
        
        try:
            async with self.session.post(url, headers=headers, params=params, json=data, allow_redirects=False) as response:
                result = await self._parse_json_response(response, "创建目录")
                if result is None:
                    return None
                if result.get("code") == 0 and result.get("data") and result["data"].get("fid"):
                    return result["data"]["fid"]
        except Exception as e:
            logger.error(f"创建目录异常: {str(e)}")
        
        return None

    async def mkdir(self, dir_path: str) -> Optional[Dict[str, Any]]:
        """
        通过路径创建目录
        
        Args:
            dir_path: 目录路径 (如 "/收藏TV/Movies")
            
        Returns:
            创建响应，包含新目录的 fid
        """
        url = f"{self.BASE_URL}/1/clouddrive/file"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        data = {
            "pdir_fid": "0",
            "file_name": "",
            "dir_path": dir_path,
            "dir_init_lock": False,
        }
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)
        
        try:
            async with self.session.post(url, headers=headers, params=params, json=data, allow_redirects=False) as response:
                result = await self._parse_json_response(response, "创建目录")
                if result is None:
                    return None
                if result.get("code") == 0:
                    return result
                logger.error(f"创建目录失败: path={dir_path}, code={result.get('code')}, message={result.get('message') or result.get('msg')}, response={result}")
        except Exception as e:
            logger.error(f"创建目录异常: path={dir_path}, error={str(e)}")
        
        return None

    async def rename(self, fid: str, new_name: str) -> bool:
        """
        重命名文件
        
        Args:
            fid: 文件 ID
            new_name: 新文件名
            
        Returns:
            是否成功
        """
        url = f"{self.BASE_URL}/1/clouddrive/file/rename"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        data = {"fid": fid, "file_name": new_name}
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)
        
        try:
            async with self.session.post(url, headers=headers, params=params, json=data, allow_redirects=False) as response:
                result = await self._parse_json_response(response, "重命名")
                if result is None:
                    return False
                if result.get("code") == 0:
                    return True
                logger.error(
                    "重命名失败: fid=%s, new_name=%s, code=%s, message=%s, response=%s",
                    fid,
                    new_name,
                    result.get("code"),
                    result.get("message") or result.get("msg"),
                    result,
                )
        except Exception as e:
            logger.error(f"重命名异常: {str(e)}")
        
        return False

    async def move_file(self, fid_list: List[str], to_pdir_fid: str, current_dir_fid: Optional[str] = None) -> bool:
        """
        移动文件到目标目录。
        """
        if not fid_list:
            return True

        url = f"{self.BASE_URL}/1/clouddrive/file/move"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        normalized_fids = [str(fid) for fid in fid_list]
        data = {
            "action_type": 1,
            "fid_list": normalized_fids,
            "filelist": normalized_fids,
            "to_pdir_fid": str(to_pdir_fid),
        }
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)

        try:
            async with self.session.post(url, headers=headers, params=params, json=data, allow_redirects=False) as response:
                result = await self._parse_json_response(response, "移动文件")
                if result is None:
                    return False
                if result.get("code") == 0:
                    return True
                logger.error(
                    "移动文件失败: fid_list=%s, to_pdir_fid=%s, current_dir_fid=%s, code=%s, message=%s, response=%s",
                    fid_list,
                    to_pdir_fid,
                    current_dir_fid,
                    result.get("code"),
                    result.get("message") or result.get("msg"),
                    result,
                )
        except Exception as e:
            logger.error(f"移动文件异常: {str(e)}")

        return False

    async def delete_file(self, fid_list: List[str]) -> bool:
        """
        删除文件或目录（移入回收站）。
        """
        if not fid_list:
            return True

        url = f"{self.BASE_URL}/1/clouddrive/file/delete"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        normalized_fids = [str(fid) for fid in fid_list]
        data = {
            "action_type": 2,
            "fid_list": normalized_fids,
            "filelist": normalized_fids,
            "exclude_fids": [],
        }
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)

        try:
            async with self.session.post(url, headers=headers, params=params, json=data, allow_redirects=False) as response:
                result = await self._parse_json_response(response, "删除文件")
                if result is None:
                    return False
                if result.get("code") == 0:
                    return True
                logger.error(
                    "删除文件失败: fid_list=%s, code=%s, message=%s, response=%s",
                    fid_list,
                    result.get("code"),
                    result.get("message") or result.get("msg"),
                    result,
                )
        except Exception as e:
            logger.error(f"删除文件异常: {str(e)}")

        return False

    async def batch_delete(self, fid_list: List[str], batch_size: int = 50, delay_seconds: float = 0.2) -> int:
        """
        批量删除文件或目录，返回成功提交删除的 fid 数量。
        """
        if not fid_list:
            return 0

        deleted_count = 0
        for index in range(0, len(fid_list), batch_size):
            batch = fid_list[index:index + batch_size]
            ok = await self.delete_file(batch)
            if ok:
                deleted_count += len(batch)
            else:
                logger.warning(f"批量删除部分失败: batch_start={index}, size={len(batch)}")
            if delay_seconds > 0 and (index + batch_size) < len(fid_list):
                await asyncio.sleep(delay_seconds)
        return deleted_count

    async def ls_dir(self, pdir_fid: str) -> Dict[str, Any]:
        """
        列出目录内容
        
        Args:
            pdir_fid: 目录 ID
            
        Returns:
            包含文件列表的响应
        """
        all_files = []
        page = 1
        
        while True:
            url = f"{self.BASE_URL}/1/clouddrive/file/sort"
            params = {
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": "50",
                "_fetch_total": "1",
                "_fetch_sub_dirs": "0",
                "_sort": "file_type:asc,updated_at:desc",
            }
            headers = self._build_headers(include_cookie=not self.mparam)
            
            try:
                async with self.session.get(url, headers=headers, params=params, allow_redirects=False) as response:
                    if response.status != 200 or not (response.content_type and "json" in response.content_type):
                        break
                    
                    result = await response.json()
                    if result.get("code") != 0:
                        break
                    
                    file_list = result.get("data", {}).get("list", [])
                    if not file_list:
                        break
                    
                    all_files.extend(file_list)
                    total = result.get("metadata", {}).get("_total", 0)
                    if len(all_files) >= total:
                        break
                    page += 1
            except Exception as e:
                logger.error(f"列出目录异常: {str(e)}")
                break
        
        return {"code": 0, "data": {"list": all_files}}

    def extract_url(self, url: str) -> Tuple[Optional[str], str]:
        """
        解析分享链接
        
        Args:
            url: 夸克分享链接
            
        Returns:
            (pwd_id, passcode)
        """
        match_id = re.search(r"/s/(\w+)", url)
        pwd_id = match_id.group(1) if match_id else None
        match_pwd = re.search(r"pwd=(\w+)", url)
        passcode = match_pwd.group(1) if match_pwd else ""
        return pwd_id, passcode

    async def validate_share_link(self, share_url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        验证分享链接是否有效
        
        Args:
            share_url: 夸克分享链接
            
        Returns:
            (is_valid, pwd_id, stoken)
        """
        pwd_id, passcode = self.extract_url(share_url)
        if not pwd_id:
            return False, None, None
        
        stoken = await self.get_stoken(pwd_id, passcode)
        if stoken:
            return True, pwd_id, stoken
        
        return False, pwd_id, None

    async def get_fid_by_path(self, path: str) -> Optional[str]:
        """
        根据路径获取目录 ID
        
        Args:
            path: 目录路径
            
        Returns:
            目录 ID 或 None
        """
        result = await self.mkdir(path)
        if result and result.get("code") == 0 and result.get("data"):
            return result["data"].get("fid")
        return None

    async def transfer_share(
        self, 
        share_url: str, 
        target_dir: str = "/收藏TV"
    ) -> Tuple[bool, str, List[Dict], str]:
        """
        转存分享链接中的文件
        
        Args:
            share_url: 分享链接
            target_dir: 目标目录
            
        Returns:
            (success, message, transferred_files, task_id)
        """
        is_valid, pwd_id, stoken = await self.validate_share_link(share_url)
        if not is_valid:
            return False, "分享链接无效或已失效", [], ""
        
        files, _ = await self.get_share_files(pwd_id, stoken)
        if not files:
            return False, "分享链接中没有文件", [], ""
        
        target_fid = await self.get_fid_by_path(target_dir)
        if not target_fid:
            return False, f"创建目标目录 {target_dir} 失败", [], ""
        
        fid_list = [f.fid for f in files]
        fid_token_list = [f.share_fid_token for f in files]
        
        result = await self.save_files(fid_list, fid_token_list, target_fid, pwd_id, stoken)
        
        if not result:
            return False, "转存失败", [], ""
            
        task_id = result.get("task_id", "")
        
        transferred_files = [
            {"fid": f.fid, "name": f.title, "size": f.size, "dir": f.file_type == 2}
            for f in files
        ]
        
        return True, "转存成功", transferred_files, task_id

    async def get_detail(self, pwd_id: str, stoken: str, pdir_fid: str = "0") -> Dict[str, Any]:
        """
        获取分享文件列表（兼容旧接口）
        
        Args:
            pwd_id: 分享ID
            stoken: 分享token
            pdir_fid: 父目录ID
            
        Returns:
            包含文件列表的响应
        """
        all_files = []
        page = 1
        have_next = True
        
        while have_next:
            files, have_next = await self.get_share_files(pwd_id, stoken, page=page, pdir_fid=pdir_fid)
            all_files.extend(files)
            page += 1
        
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "fid": f.fid,
                        "file_name": f.title,
                        "size": f.size,
                        "dir": f.file_type == 2,
                        "pdir_fid": f.pdir_fid,
                        "share_fid_token": f.share_fid_token
                    }
                    for f in all_files
                ]
            }
        }

    async def save_file(
        self,
        fid_list: List[str],
        fid_token_list: List[str],
        to_pdir_fid: str,
        pwd_id: str,
        stoken: str
    ) -> Dict[str, Any]:
        """
        转存文件到指定目录（兼容旧接口）
        
        Args:
            fid_list: 文件ID列表
            fid_token_list: 文件token列表
            to_pdir_fid: 目标目录ID
            pwd_id: 分享ID
            stoken: 分享token
            
        Returns:
            转存响应
        """
        result = await self.save_files(fid_list, fid_token_list, to_pdir_fid, pwd_id, stoken)
        if result:
            return {"status": 200, "code": 0, "data": result}
        return {"status": 500, "code": 1, "message": "转存失败"}

    async def query_task(self, task_id: str, max_retries: int = 20) -> Dict[str, Any]:
        """
        查询任务状态（兼容旧接口）
        
        Args:
            task_id: 任务ID
            max_retries: 最大重试次数
            
        Returns:
            任务状态响应
        """
        for retry_index in range(max_retries):
            status = await self.get_task_status(task_id, retry_index)
            if status and status.status == 2:
                return {"status": 200, "data": {"status": 2}}
            import asyncio
            await asyncio.sleep(0.5)
        
        return {"status": 500, "message": "任务超时"}
