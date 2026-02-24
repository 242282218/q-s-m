"""
转存服务
协调 QuarkTransferClient 和 Renamer 完成转存和重命名任务
"""
import logging
from typing import Optional, List, Dict, Tuple

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from ..db.models import Collection, TransferHistory
from ..collection.service import CollectionService
from ..quark.core.transfer_client import QuarkTransferClient
from .renamer import Renamer

logger = logging.getLogger(__name__)


class TransferService:
    """转存服务"""

    def __init__(self, db: Session, cookie: str = ""):
        self.db = db
        self._cookie = cookie
        self.renamer = Renamer()
        self.collection_service = CollectionService(db)
        self._quark_client: Optional[QuarkTransferClient] = None
    
    async def _get_client(self) -> QuarkTransferClient:
        if self._quark_client is None or self._quark_client.cookie != self._cookie:
            if self._quark_client:
                await self._quark_client.close()
            self._quark_client = QuarkTransferClient(self._cookie)
            logger.debug("创建新的 QuarkTransferClient 实例")
        return self._quark_client
    
    async def get_quark(self) -> QuarkTransferClient:
        """获取夸克客户端（异步方法）"""
        return await self._get_client()
    
    async def close(self) -> None:
        """关闭夸克客户端连接"""
        if self._quark_client:
            await self._quark_client.close()
            self._quark_client = None
            logger.debug("QuarkTransferClient 连接已关闭")

    async def validate_link(self, share_url: str) -> Tuple[bool, str, List[Dict]]:
        """
        验证分享链接有效性并获取文件列表
        
        Args:
            share_url: 分享链接
            
        Returns:
            (valid, message, files)
        """
        logger.info(f"验证分享链接: {share_url[:50]}...")
        
        try:
            client = await self._get_client()
            is_valid, pwd_id, stoken = await client.validate_share_link(share_url)
            
            if not is_valid:
                logger.warning(f"分享链接无效: {share_url[:50]}...")
                return False, "链接无效或已失效", []
            
            detail_resp = await client.get_detail(pwd_id, stoken, "0")
            if detail_resp.get("code") != 0:
                error_msg = detail_resp.get("message", "获取文件列表失败")
                logger.error(f"获取文件列表失败: {error_msg}")
                return False, error_msg, []
            
            files = []
            for f in detail_resp.get("data", {}).get("list", []):
                files.append({
                    "fid": f.get("fid"),
                    "name": f.get("file_name"),
                    "size": f.get("size", 0),
                    "is_dir": f.get("dir", False),
                })
            
            logger.info(f"链接验证成功，共 {len(files)} 个文件")
            return True, "链接有效", files
            
        except Exception as e:
            logger.error(f"验证链接异常: {e}", exc_info=True)
            return False, f"验证失败: {str(e)}", []

    async def transfer_collection(
        self,
        collection_id: int,
        target_folder: Optional[str] = None,
        auto_rename: bool = True,
    ) -> Tuple[bool, str, List[Dict]]:
        """
        转存收藏中的资源
        
        Args:
            collection_id: 收藏 ID
            target_folder: 目标目录 (可选，默认根据分类确定)
            auto_rename: 是否自动重命名
            
        Returns:
            (success, message, transferred_files)
        """
        logger.info(f"开始转存: collection_id={collection_id}, auto_rename={auto_rename}")
        
        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            logger.warning(f"转存失败 - 收藏不存在: id={collection_id}")
            return False, "收藏不存在", []
        
        share_url = collection.quark_share_url
        title = collection.title
        
        try:
            client = await self._get_client()
            is_valid, pwd_id, stoken = await client.validate_share_link(share_url)
            if not is_valid:
                self.collection_service.update_status(collection_id, 2)
                logger.warning(f"转存失败 - 分享链接已失效: id={collection_id}, title={title}")
                return False, "分享链接已失效", []
            
            if not target_folder:
                target_folder = self._get_target_folder(collection)
            
            logger.info(f"目标目录: {target_folder}")
            
            detail_resp = await client.get_detail(pwd_id, stoken, "0")
            if detail_resp.get("code") != 0:
                error_msg = detail_resp.get("message", "获取文件列表失败")
                logger.error(f"获取文件列表失败: {error_msg}")
                return False, f"获取文件列表失败: {error_msg}", []
            
            file_list = detail_resp.get("data", {}).get("list", [])
            if not file_list:
                logger.warning(f"分享链接中没有文件: id={collection_id}")
                return False, "分享链接中没有文件", []
            
            renamed_files = []
            if auto_rename:
                for f in file_list:
                    if f.get("dir"):
                        continue
                    result = self.renamer.generate_path(
                        original_filename=f.get("file_name", ""),
                        title=collection.title,
                        year=collection.year,
                        media_type=collection.media_type,
                        category=collection.category,
                    )
                    renamed_files.append({
                        "fid": f.get("fid"),
                        "original_name": f.get("file_name"),
                        "new_name": result.new_name,
                        "new_path": result.new_path,
                        "season": result.season,
                        "episode": result.episode,
                    })
                logger.info(f"准备重命名 {len(renamed_files)} 个文件")
            
            target_fid = await client.get_fid_by_path(target_folder)
            if not target_fid:
                logger.error(f"创建目标目录失败: {target_folder}")
                return False, f"创建目标目录失败: {target_folder}", []
            
            fid_list = [f["fid"] for f in file_list]
            fid_token_list = [f.get("share_fid_token", "") for f in file_list]
            
            save_resp = await client.save_file(fid_list, fid_token_list, target_fid, pwd_id, stoken)
            
            if save_resp.get("status") != 200 and save_resp.get("code") != 0:
                error_msg = save_resp.get("message", "未知错误")
                logger.error(f"转存失败: {error_msg}")
                return False, f"转存失败: {error_msg}", []
            
            task_id = save_resp.get("data", {}).get("task_id")
            if task_id:
                task_resp = await client.query_task(task_id)
                if task_resp.get("data", {}).get("status") != 2:
                    logger.warning(f"转存任务未完成: task_id={task_id}")
                    return False, "转存任务未完成", []
            
            ls_resp = await client.ls_dir(target_fid)
            saved_files = []
            if ls_resp.get("code") == 0:
                saved_files = ls_resp.get("data", {}).get("list", [])
                
                if auto_rename and renamed_files:
                    rename_map = {item["original_name"]: item for item in renamed_files}
                    rename_count = 0
                    
                    for saved_file in saved_files:
                        original_name = saved_file.get("file_name")
                        if original_name in rename_map:
                            plan = rename_map[original_name]
                            fid = saved_file.get("fid")
                            new_name = plan["new_name"]
                            
                            try:
                                await client.rename(fid, new_name)
                                saved_file["file_name"] = new_name
                                rename_count += 1
                            except Exception as e:
                                logger.warning(f"重命名失败: {original_name} -> {new_name}, error={e}")
                    
                    if rename_count > 0:
                        logger.info(f"成功重命名 {rename_count} 个文件")
                    file_list = saved_files
            
            for f in file_list:
                history = TransferHistory(
                    collection_id=collection_id,
                    quark_fid=f.get("fid", ""),
                    local_path=target_folder,
                    file_name=f.get("file_name", ""),
                    file_size=f.get("size"),
                )
                self.db.add(history)
            
            self.db.commit()
            
            self.collection_service.update_status(collection_id, 1)
            
            transferred_files = []
            for f in file_list:
                transferred_files.append({
                    "fid": f.get("fid"),
                    "name": f.get("file_name"),
                    "size": f.get("size"),
                    "path": target_folder,
                })
            
            logger.info(f"转存成功: id={collection_id}, title={title}, files={len(transferred_files)}")
            return True, "转存成功", transferred_files
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"转存失败 - 数据库错误: id={collection_id}, error={e}")
            return False, "转存失败: 数据库错误", []
        except Exception as e:
            logger.error(f"转存失败 - 未知错误: id={collection_id}, error={e}", exc_info=True)
            return False, f"转存失败: {str(e)}", []

    def _get_target_folder(self, collection: Collection) -> str:
        """
        根据收藏信息确定目标目录
        
        Args:
            collection: 收藏对象
            
        Returns:
            目标目录路径
        """
        category = collection.category or collection.media_type
        
        base_dirs = {
            'movie': '/收藏TV/Movies',
            'tv': '/收藏TV/TV Shows',
            'anime': '/收藏TV/Anime',
            'documentary': '/收藏TV/Documentary',
        }
        
        base_dir = base_dirs.get(category, '/收藏TV/Movies')
        
        title = self.renamer.sanitize_filename(collection.title)
        if collection.year:
            folder_name = f"{title} ({collection.year})"
        else:
            folder_name = title
        
        return f"{base_dir}/{folder_name}"
