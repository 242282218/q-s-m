"""
夸克转存服务
直接实现夸克转存功能，提供转存服务
"""
import logging
import re
from typing import Optional, Dict, Any, List

from app.core.config import get_settings
from app.quark.core.transfer_client import QuarkTransferClient
from app.quark.core.transfer_models import ShareInfo, FileDetail, TransferResult
from app.quark.core.transfer_utils import parse_share_url, random_delay

settings = get_settings()
logger = logging.getLogger(__name__)


class TransferService:
    """
    夸克转存服务，直接实现转存功能
    """
    
    def __init__(self):
        """
        初始化转存服务
        """
        self.cookie = settings.quark_cookie

    @staticmethod
    def _sanitize_dir_name(name: str) -> str:
        sanitized = re.sub(r'[\\/:*?"<>|]', " ", name or "").strip()
        sanitized = re.sub(r"\s+", " ", sanitized).strip()
        return sanitized
    
    async def parse_share_url(self, share_url: str) -> Optional[ShareInfo]:
        """
        解析分享链接并获取分享信息
        
        Args:
            share_url: 夸克分享链接
            
        Returns:
            ShareInfo: 分享信息，失败返回None
        """
        pwd_id = parse_share_url(share_url)
        if not pwd_id:
            return None
        
        async with QuarkTransferClient(self.cookie) as client:
            stoken = await client.get_stoken(pwd_id)
            if not stoken:
                return None
            
            return ShareInfo(
                pwd_id=pwd_id,
                stoken=stoken,
                title="",
                total_files=0
            )
    
    async def get_all_files(self, share_info: ShareInfo, pdir_fid: str = "0") -> List[FileDetail]:
        """
        获取分享链接的所有文件（支持分页）
        
        Args:
            share_info: 分享信息
            pdir_fid: 父目录ID
            
        Returns:
            List[FileDetail]: 所有文件列表
        """
        all_files = []
        page = 1
        have_next = True
        
        async with QuarkTransferClient(self.cookie) as client:
            while have_next:
                await random_delay()
                files, have_next = await client.get_share_files(
                    share_info.pwd_id,
                    share_info.stoken,
                    page=page,
                    pdir_fid=pdir_fid
                )
                all_files.extend(files)
                page += 1
                
                if len(files) == 0:
                    break
        
        share_info.total_files = len(all_files)
        return all_files
    
    async def transfer_batch(self, file_list: List[FileDetail], share_info: ShareInfo, to_dir_fid: str) -> TransferResult:
        """
        批量转存文件
        
        Args:
            file_list: 文件列表
            share_info: 分享信息
            to_dir_fid: 目标目录ID
            
        Returns:
            TransferResult: 转存结果
        """
        if not file_list:
            return TransferResult(
                success=False,
                message="文件列表为空"
            )
        
        fid_list = [f.fid for f in file_list]
        fid_token_list = [f.share_fid_token for f in file_list]
        
        async with QuarkTransferClient(self.cookie) as client:
            result = await client.save_files(
                fid_list=fid_list,
                fid_token_list=fid_token_list,
                to_pdir_fid=to_dir_fid,
                pwd_id=share_info.pwd_id,
                stoken=share_info.stoken
            )
        
        if result:
            task_id = result.get("task_id", "")
            return TransferResult(
                success=True,
                task_id=task_id,
                message=f"批量转存 {len(file_list)} 个文件成功",
                saved_files=fid_list
            )
        
        return TransferResult(
            success=False,
            message=f"批量转存 {len(file_list)} 个文件失败"
        )
    
    async def transfer_resource(
        self,
        link: str,
        to_dir_fid: str = "0",
        to_dir_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        转存资源
        
        Args:
            link: 夸克分享链接
            to_dir_fid: 目标目录ID
            to_dir_name: 目标目录名称
            
        Returns:
            转存结果
        """
        try:
            # 检查Cookie是否配置
            if not self.cookie:
                return {
                    "success": False,
                    "message": "夸克网盘Cookie未配置",
                    "task_id": "",
                    "saved_files": []
                }
            
            # 解析分享链接
            share_info = await self.parse_share_url(link)
            if not share_info:
                return {
                    "success": False,
                    "message": "解析分享链接失败",
                    "task_id": "",
                    "saved_files": []
                }
            
            # 获取所有文件
            files = await self.get_all_files(share_info)
            if not files:
                return {
                    "success": False,
                    "message": "分享链接中没有文件",
                    "task_id": "",
                    "saved_files": []
                }

            target_dir_fid = to_dir_fid
            if to_dir_name:
                safe_dir_name = self._sanitize_dir_name(to_dir_name)
                if not safe_dir_name:
                    return {
                        "success": False,
                        "message": "目录名称无效",
                        "task_id": "",
                        "saved_files": []
                    }
                created_dir_fid = await self.create_directory(safe_dir_name, pdir_fid=to_dir_fid)
                if not created_dir_fid:
                    return {
                        "success": False,
                        "message": "创建目录失败",
                        "task_id": "",
                        "saved_files": []
                    }
                target_dir_fid = created_dir_fid
            
            # 执行转存
            result = await self.transfer_batch(files, share_info, target_dir_fid)
            
            return {
                "success": result.success,
                "message": result.message,
                "task_id": result.task_id,
                "saved_files": result.saved_files
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"转存失败: {str(e)}",
                "task_id": "",
                "saved_files": []
            }

    async def get_task_status(self, task_id: str, retry_index: int = 0) -> Dict[str, Any]:
        """
        查询转存任务状态
        
        Args:
            task_id: 任务ID
            retry_index: 重试索引
            
        Returns:
            任务状态
        """
        try:
            # 检查Cookie是否配置
            if not self.cookie:
                return {
                    "success": False,
                    "message": "夸克网盘Cookie未配置"
                }
            
            async with QuarkTransferClient(self.cookie) as client:
                status = await client.get_task_status(task_id, retry_index)
                if status:
                    return {
                        "success": True,
                        "task_id": status.task_id,
                        "status": status.status,
                        "message": status.message,
                        "progress": status.progress,
                        "is_success": status.is_success,
                        "is_failed": status.is_failed
                    }
                else:
                    return {
                        "success": False,
                        "message": "查询任务状态失败"
                    }
        except Exception as e:
            return {
                "success": False,
                "message": f"查询任务状态失败: {str(e)}"
            }
    
    async def create_directory(self, dir_name: str, pdir_fid: str = "0") -> Optional[str]:
        """
        创建目录
        
        Args:
            dir_name: 目录名称
            pdir_fid: 父目录ID
            
        Returns:
            目录ID，失败返回None
        """
        try:
            if not self.cookie:
                logger.error("创建目录失败: 夸克网盘Cookie未配置")
                return None
            
            async with QuarkTransferClient(self.cookie) as client:
                return await client.create_dir(dir_name, pdir_fid)
        except Exception as e:
            logger.error(f"创建目录失败: {str(e)}")
            return None

