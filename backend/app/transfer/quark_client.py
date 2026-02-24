"""
夸克网盘 API 客户端
移植自 quark-auto-save 项目，用于转存和重命名文件
"""
import re
import random
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
import httpx
import tenacity

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class QuarkTransferClient:
    """夸克网盘转存客户端"""
    
    BASE_URL = "https://drive-pc.quark.cn"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"

    def __init__(self, cookie: str = ""):
        settings = get_settings()
        self.cookie = cookie.strip() if cookie else getattr(settings, 'quark_cookie', '')
        self.savepath_fid: Dict[str, str] = {"/": "0"}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "cookie": self.cookie,
                    "content-type": "application/json",
                    "user-agent": self.USER_AGENT,
                }
            )
        return self._client

    async def close(self):
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
        retry=tenacity.retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        before_sleep=lambda retry_state: logger.warning(
            f"请求失败，第 {retry_state.attempt_number} 次重试: {retry_state.outcome.exception()}"
        )
    )
    async def _send_request(self, method: str, url: str, **kwargs) -> Dict:
        """发送请求（带自动重试）"""
        client = await self._get_client()
        try:
            response = await client.request(method, url, **kwargs)
            return response.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            raise  # 让tenacity处理重试
        except Exception as e:
            logger.error(f"请求失败: {method} {url} - {str(e)}")
            return {"status": 500, "code": 1, "message": f"请求失败: {str(e)}"}

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

    async def get_stoken(self, pwd_id: str, passcode: str = "") -> Optional[str]:
        """
        获取 stoken，同时验证链接有效性
        
        Args:
            pwd_id: 分享 ID
            passcode: 提取码
            
        Returns:
            stoken 或 None (链接无效)
        """
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/token"
        params = {"pr": "ucpro", "fr": "pc"}
        payload = {"pwd_id": pwd_id, "passcode": passcode}
        
        response = await self._send_request("POST", url, params=params, json=payload)
        
        if response.get("status") == 200 and response.get("data"):
            return response["data"].get("stoken")
        return None

    async def get_detail(
        self, 
        pwd_id: str, 
        stoken: str, 
        pdir_fid: str = "0"
    ) -> Dict:
        """
        获取分享文件列表
        
        Args:
            pwd_id: 分享 ID
            stoken: 分享 Token
            pdir_fid: 父目录 ID (0 为根目录)
            
        Returns:
            包含文件列表的响应
        """
        list_merge = []
        page = 1
        
        while True:
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
            }
            
            response = await self._send_request("GET", url, params=params)
            
            if response.get("code") != 0:
                return response
            
            file_list = response.get("data", {}).get("list", [])
            if file_list:
                list_merge.extend(file_list)
                page += 1
            else:
                break
            
            total = response.get("metadata", {}).get("_total", 0)
            if len(list_merge) >= total:
                break
        
        response["data"]["list"] = list_merge
        return response

    async def save_file(
        self,
        fid_list: List[str],
        fid_token_list: List[str],
        to_pdir_fid: str,
        pwd_id: str,
        stoken: str
    ) -> Dict:
        """
        转存文件到指定目录
        
        Args:
            fid_list: 文件 ID 列表
            fid_token_list: 文件 Token 列表
            to_pdir_fid: 目标目录 ID
            pwd_id: 分享 ID
            stoken: 分享 Token
            
        Returns:
            转存响应
        """
        url = f"{self.BASE_URL}/1/clouddrive/share/sharepage/save"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "app": "clouddrive",
            "__dt": int(random.uniform(1, 5) * 60 * 1000),
            "__t": datetime.now().timestamp(),
        }
        payload = {
            "fid_list": fid_list,
            "fid_token_list": fid_token_list,
            "to_pdir_fid": to_pdir_fid,
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": "0",
            "scene": "link",
        }
        
        return await self._send_request("POST", url, params=params, json=payload)

    async def query_task(self, task_id: str, max_retries: int = 20) -> Dict:
        """
        查询任务状态
        
        Args:
            task_id: 任务 ID
            max_retries: 最大重试次数
            
        Returns:
            任务状态响应
        """
        retry_index = 0
        
        while retry_index < max_retries:
            url = f"{self.BASE_URL}/1/clouddrive/task"
            params = {
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "task_id": task_id,
                "retry_index": retry_index,
                "__dt": int(random.uniform(1, 5) * 60 * 1000),
                "__t": datetime.now().timestamp(),
            }
            
            response = await self._send_request("GET", url, params=params)
            
            if response.get("status") != 200:
                return response
            
            status = response.get("data", {}).get("status")
            if status == 2:  # 完成
                return response
            
            retry_index += 1
            await self._async_sleep(0.5)
        
        return {"status": 500, "message": "任务超时"}

    async def _async_sleep(self, seconds: float):
        """异步等待"""
        import asyncio
        await asyncio.sleep(seconds)

    async def mkdir(self, dir_path: str) -> Dict:
        """
        创建目录
        
        Args:
            dir_path: 目录路径 (如 "/收藏TV/Movies")
            
        Returns:
            创建响应，包含新目录的 fid
        """
        url = f"{self.BASE_URL}/1/clouddrive/file"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        payload = {
            "pdir_fid": "0",
            "file_name": "",
            "dir_path": dir_path,
            "dir_init_lock": False,
        }
        
        response = await self._send_request("POST", url, params=params, json=payload)
        
        # 缓存目录 fid
        if response.get("code") == 0 and response.get("data"):
            fid = response["data"].get("fid")
            if fid:
                self.savepath_fid[dir_path] = fid
        
        return response

    async def rename(self, fid: str, new_name: str) -> Dict:
        """
        重命名文件
        
        Args:
            fid: 文件 ID
            new_name: 新文件名
            
        Returns:
            重命名响应
        """
        url = f"{self.BASE_URL}/1/clouddrive/file/rename"
        params = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        payload = {"fid": fid, "file_name": new_name}
        
        return await self._send_request("POST", url, params=params, json=payload)

    async def ls_dir(self, pdir_fid: str) -> Dict:
        """
        列出目录内容
        
        Args:
            pdir_fid: 目录 ID
            
        Returns:
            目录内容响应
        """
        list_merge = []
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
            
            response = await self._send_request("GET", url, params=params)
            
            if response.get("code") != 0:
                return response
            
            file_list = response.get("data", {}).get("list", [])
            if file_list:
                list_merge.extend(file_list)
                page += 1
            else:
                break
            
            total = response.get("metadata", {}).get("_total", 0)
            if len(list_merge) >= total:
                break
        
        response["data"]["list"] = list_merge
        return response

    async def get_fid_by_path(self, path: str) -> Optional[str]:
        """
        根据路径获取目录 ID
        
        Args:
            path: 目录路径
            
        Returns:
            目录 ID 或 None
        """
        if path in self.savepath_fid:
            return self.savepath_fid[path]
        
        # 尝试创建目录
        response = await self.mkdir(path)
        if response.get("code") == 0 and response.get("data"):
            fid = response["data"].get("fid")
            if fid:
                self.savepath_fid[path] = fid
                return fid
        
        return None

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

    async def transfer_share(
        self, 
        share_url: str, 
        target_dir: str = "/收藏TV"
    ) -> Tuple[bool, str, List[Dict]]:
        """
        转存分享链接中的文件
        
        Args:
            share_url: 分享链接
            target_dir: 目标目录
            
        Returns:
            (success, message, transferred_files)
        """
        # 1. 验证链接
        is_valid, pwd_id, stoken = await self.validate_share_link(share_url)
        if not is_valid:
            return False, "分享链接无效或已失效", []
        
        # 2. 获取文件列表
        detail_resp = await self.get_detail(pwd_id, stoken, "0")
        if detail_resp.get("code") != 0:
            return False, f"获取文件列表失败: {detail_resp.get('message', '未知错误')}", []
        
        file_list = detail_resp.get("data", {}).get("list", [])
        if not file_list:
            return False, "分享链接中没有文件", []
        
        # 3. 创建目标目录
        target_fid = await self.get_fid_by_path(target_dir)
        if not target_fid:
            return False, f"创建目标目录 {target_dir} 失败", []
        
        # 4. 转存文件
        fid_list = [f["fid"] for f in file_list]
        fid_token_list = [f.get("share_fid_token", "") for f in file_list]
        
        save_resp = await self.save_file(fid_list, fid_token_list, target_fid, pwd_id, stoken)
        
        if save_resp.get("status") != 200 and save_resp.get("code") != 0:
            return False, f"转存失败: {save_resp.get('message', '未知错误')}", []
        
        # 5. 等待任务完成
        task_id = save_resp.get("data", {}).get("task_id")
        if task_id:
            task_resp = await self.query_task(task_id)
            if task_resp.get("data", {}).get("status") != 2:
                return False, "转存任务未完成", []
        
        # 6. 构建返回结果
        transferred_files = []
        for f in file_list:
            transferred_files.append({
                "fid": f["fid"],
                "name": f.get("file_name", ""),
                "size": f.get("size", 0),
                "dir": f.get("dir", False),
            })
        
        return True, "转存成功", transferred_files
