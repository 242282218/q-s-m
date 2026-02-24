"""
夸克转存客户端
"""
import time
import random
import logging
import re
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
        self.session = aiohttp.ClientSession()
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 "
            "Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"
        )
        self.mparam = self._match_mparam_from_cookie(cookie)
        self._load_cookies(cookie)

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
        if cookies:
            for base_url in ("https://pan.quark.cn", "https://drive-pc.quark.cn", "https://drive-m.quark.cn"):
                self.session.cookie_jar.update_cookies(cookies, response_url=URL(base_url))
        
    async def __aenter__(self):
        """
        异步上下文管理器进入
        """
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        异步上下文管理器退出
        """
        await self.session.close()

    def _build_headers(self, json_body: bool = False, include_cookie: bool = True) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        if not include_cookie:
            headers["Cookie"] = ""
        return headers

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
    
    async def get_stoken(self, pwd_id: str) -> Optional[str]:
        """
        获取分享的stoken
        
        Args:
            pwd_id: 分享ID
            
        Returns:
            stoken，失败返回None
        """
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/token"
        params = {"pr": "ucpro", "fr": "pc"}
        params["uc_param_str"] = ""
        url, params = self._apply_mobile_share_params(url, params)
        headers = self._build_headers(json_body=True, include_cookie=not self.mparam)
        payload = {"pwd_id": pwd_id, "passcode": ""}
        
        try:
            async with self.session.post(url, headers=headers, params=params, json=payload, allow_redirects=False) as response:
                if response.status in (301, 302, 303, 307, 308):
                    logger.error(f"获取stoken被重定向: {response.headers.get('location')}")
                    return None
                if response.status == 200:
                    if response.content_type and "json" in response.content_type:
                        data = await response.json()
                    else:
                        logger.error(f"获取stoken返回非JSON: {response.content_type}")
                        return None
                    if data.get("data") and data["data"].get("stoken") and data.get("code") == 0:
                        return data["data"]["stoken"]
                    logger.error(f"获取stoken失败: {data.get('message') or data.get('msg')}")
                logger.error(f"获取stoken失败，响应状态: {response.status}")
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
                if response.status in (301, 302, 303, 307, 308):
                    logger.error(f"获取分享文件被重定向: {response.headers.get('location')}")
                    return [], False
                if response.status == 200:
                    if response.content_type and "json" in response.content_type:
                        data = await response.json()
                    else:
                        logger.error(f"获取分享文件返回非JSON: {response.content_type}")
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
                logger.error(f"获取分享文件失败，响应状态: {response.status}")
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
                if response.status in (301, 302, 303, 307, 308):
                    logger.error(f"保存文件被重定向: {response.headers.get('location')}")
                    return None
                if response.status == 200:
                    if response.content_type and "json" in response.content_type:
                        result = await response.json()
                    else:
                        logger.error(f"保存文件返回非JSON: {response.content_type}")
                        return None
                    if result.get("code") == 0 and result.get("data"):
                        return result["data"]
                    logger.error(f"保存文件失败: {result.get('message') or result.get('msg')}")
                logger.error(f"保存文件失败，响应状态: {response.status}")
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
                if response.status in (301, 302, 303, 307, 308):
                    logger.error(f"获取任务状态被重定向: {response.headers.get('location')}")
                    return None
                if response.status == 200:
                    if response.content_type and "json" in response.content_type:
                        data = await response.json()
                    else:
                        logger.error(f"获取任务状态返回非JSON: {response.content_type}")
                        return None
                    if data.get("code") == 0 and data.get("data"):
                        status_data = data["data"]
                        return TaskStatus(
                            task_id=task_id,
                            status=status_data.get("status", 0),
                            message=status_data.get("message") or status_data.get("task_title", ""),
                            progress=status_data.get("progress", 0)
                        )
                logger.error(f"获取任务状态失败，响应状态: {response.status}")
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
                if response.status in (301, 302, 303, 307, 308):
                    logger.error(f"创建目录被重定向: {response.headers.get('location')}")
                    return None
                if response.status == 200:
                    if response.content_type and "json" in response.content_type:
                        result = await response.json()
                    else:
                        logger.error(f"创建目录返回非JSON: {response.content_type}")
                        return None
                    if result.get("code") == 0 and result.get("data") and result["data"].get("fid"):
                        return result["data"]["fid"]
                logger.error(f"创建目录失败，响应状态: {response.status}")
        except Exception as e:
            logger.error(f"创建目录异常: {str(e)}")
        
        return None
