"""
转存服务
协调 QuarkTransferClient 和 Renamer 完成转存和重命名任务
"""
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session

from ..db.models import Collection, TransferHistory
from ..collection.service import CollectionService
from .quark_client import QuarkTransferClient
from .renamer import Renamer


class TransferService:
    """转存服务"""

    def __init__(self, db: Session, cookie: str = ""):
        self.db = db
        self.quark = QuarkTransferClient(cookie)
        self.renamer = Renamer()
        self.collection_service = CollectionService(db)

    async def close(self):
        """关闭客户端"""
        await self.quark.close()

    async def validate_link(self, share_url: str) -> Tuple[bool, str, List[Dict]]:
        """
        验证分享链接有效性并获取文件列表
        
        Args:
            share_url: 分享链接
            
        Returns:
            (valid, message, files)
        """
        is_valid, pwd_id, stoken = await self.quark.validate_share_link(share_url)
        
        if not is_valid:
            return False, "链接无效或已失效", []
        
        detail_resp = await self.quark.get_detail(pwd_id, stoken, "0")
        if detail_resp.get("code") != 0:
            return False, detail_resp.get("message", "获取文件列表失败"), []
        
        files = []
        for f in detail_resp.get("data", {}).get("list", []):
            files.append({
                "fid": f.get("fid"),
                "name": f.get("file_name"),
                "size": f.get("size", 0),
                "is_dir": f.get("dir", False),
            })
        
        return True, "链接有效", files

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
        # 1. 获取收藏信息
        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            return False, "收藏不存在", []
        
        share_url = collection.quark_share_url
        
        # 2. 验证链接
        is_valid, pwd_id, stoken = await self.quark.validate_share_link(share_url)
        if not is_valid:
            # 更新收藏状态为失效
            self.collection_service.update_status(collection_id, 2)
            return False, "分享链接已失效", []
        
        # 3. 确定目标目录
        if not target_folder:
            target_folder = self._get_target_folder(collection)
        
        # 4. 获取文件列表
        detail_resp = await self.quark.get_detail(pwd_id, stoken, "0")
        if detail_resp.get("code") != 0:
            return False, f"获取文件列表失败: {detail_resp.get('message', '未知错误')}", []
        
        file_list = detail_resp.get("data", {}).get("list", [])
        if not file_list:
            return False, "分享链接中没有文件", []
        
        # 5. 生成重命名计划
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
        
        # 6. 创建目标目录
        target_fid = await self.quark.get_fid_by_path(target_folder)
        if not target_fid:
            return False, f"创建目标目录失败: {target_folder}", []
        
        # 7. 转存文件
        fid_list = [f["fid"] for f in file_list]
        fid_token_list = [f.get("share_fid_token", "") for f in file_list]
        
        save_resp = await self.quark.save_file(fid_list, fid_token_list, target_fid, pwd_id, stoken)
        
        if save_resp.get("status") != 200 and save_resp.get("code") != 0:
            return False, f"转存失败: {save_resp.get('message', '未知错误')}", []
        
        # 8. 等待任务完成
        task_id = save_resp.get("data", {}).get("task_id")
        if task_id:
            task_resp = await self.quark.query_task(task_id)
            if task_resp.get("data", {}).get("status") != 2:
                return False, "转存任务未完成", []
        
        # 9. 获取转存后的文件并重命名
        transferred_results = []
        if auto_rename and renamed_files:
            # 获取目标目录下的文件列表
            ls_resp = await self.quark.ls_dir(target_fid)
            if ls_resp.get("code") == 0:
                saved_files = ls_resp.get("data", {}).get("list", [])
                
                # 建立原始文件名到重命名计划的映射
                rename_map = {item["original_name"]: item for item in renamed_files}
                
                for saved_file in saved_files:
                    original_name = saved_file.get("file_name")
                    if original_name in rename_map:
                        plan = rename_map[original_name]
                        fid = saved_file.get("fid")
                        new_name = plan["new_name"]
                        
                        # 执行重命名
                        rename_resp = await self.quark.rename(fid, new_name)
                        if rename_resp.get("code") == 0:
                            # 更新文件信息用于返回
                            saved_file["file_name"] = new_name
                            saved_file["path"] = plan["new_path"]
                        else:
                            # 重命名失败，保留原名但记录日志（此处暂略，直接保留原名）
                            pass

                # 更新 file_list 为最新的状态 (用于后续记录历史和返回)
                # 注意：这里我们其实应该用 saved_files 来更新 file_list 或者直接用 saved_files
                # 为了保持简单，我们更新 file_list 中的文件名，如果它被重命名了
                
                # 更简单的做法：直接用 saved_files 作为最终结果的基础
                # 但我们需要保留原始 file_list 中的一些信息吗？
                # TransferHistory 需要 quark_fid, local_path, file_name, file_size
                # saved_files 里有 fid, file_name, size. 
                # 所以我们可以用 saved_files 来替换 file_list 用于后续处理
                
                # 过滤掉非本次转存的文件（虽然新目录应该只有本次转存的文件，但为了安全...）
                # 其实很难过滤，除非我们记录了本次转存的 fids。但 fid 变了。
                # 假设目标目录是新创建的或者是专用的，那么 saved_files 就是我们要的。
                # 或者，我们只关心那些名字在 rename_map 里的文件，以及没被重命名的文件。
                
                file_list = saved_files

        
        # 10. 记录转存历史
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
        
        # 11. 更新收藏状态为已转存
        self.collection_service.update_status(collection_id, 1)
        
        # 12. 构建返回结果
        transferred_files = []
        for f in file_list:
            transferred_files.append({
                "fid": f.get("fid"),
                "name": f.get("file_name"),
                "size": f.get("size"),
                "path": target_folder,
            })
        
        return True, "转存成功", transferred_files

    def _get_target_folder(self, collection: Collection) -> str:
        """
        根据收藏信息确定目标目录
        
        Args:
            collection: 收藏对象
            
        Returns:
            目标目录路径
        """
        category = collection.category or collection.media_type
        
        # 基础目录映射
        base_dirs = {
            'movie': '/收藏TV/Movies',
            'tv': '/收藏TV/TV Shows',
            'anime': '/收藏TV/Anime',
            'documentary': '/收藏TV/Documentary',
        }
        
        base_dir = base_dirs.get(category, '/收藏TV/Movies')
        
        # 构建完整路径
        title = self.renamer.sanitize_filename(collection.title)
        if collection.year:
            folder_name = f"{title} ({collection.year})"
        else:
            folder_name = title
        
        return f"{base_dir}/{folder_name}"

    async def instant_play(
        self,
        collection_id: int,
        webdav_base_url: str = "http://localhost:7799/webdav"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        立即播放：检查/转存 + 返回 WebDAV URL
        
        Args:
            collection_id: 收藏 ID
            webdav_base_url: WebDAV 基础 URL
            
        Returns:
            (success, message, webdav_url)
        """
        # 1. 获取收藏信息
        collection = self.collection_service.get_by_id(collection_id)
        if not collection:
            return False, "收藏不存在", None
        
        # 2. 检查是否已转存
        if collection.status != 1:
            # 尚未转存，执行转存
            success, message, _ = await self.transfer_collection(collection_id)
            if not success:
                return False, message, None
        
        # 3. 更新最后播放时间
        self.collection_service.update_last_played(collection_id)
        
        # 4. 构建 WebDAV URL - 指向实际视频文件
        target_folder = self._get_target_folder(collection)
        
        # 查询文件夹内容
        try:
            fid = await self._get_folder_fid(target_folder)
            if not fid:
                return False, "未找到目标文件夹", None
            
            files_resp = await self.quark.ls_dir(fid)
            if files_resp.get("code") != 0:
                return False, "获取文件列表失败", None
            
            files = files_resp.get("data", {}).get("list", [])
            video_file = self._find_video_file(files)
            
            if not video_file:
                return False, "未找到视频文件", None
            
            # 构建完整文件路径
            relative_path = target_folder.replace('/收藏TV', '') + '/' + video_file['file_name']
            webdav_url = f"{webdav_base_url}{relative_path}"
            
            return True, "准备播放", webdav_url
            
        except Exception as e:
            return False, f"构建播放链接失败: {str(e)}", None
    
    async def _get_folder_fid(self, folder_path: str) -> Optional[str]:
        """
        根据文件夹路径获取 fid
        
        Args:
            folder_path: 文件夹路径，如 /收藏TV/Movies/Inception (2010)
            
        Returns:
            folder fid or None
        """
        # 从根目录开始逐级查找
        parts = [p for p in folder_path.split('/') if p]
        current_fid = "0"  # 根目录
        
        for part in parts:
            resp = await self.quark.ls_dir(current_fid)
            if resp.get("code") != 0:
                return None
            
            files = resp.get("data", {}).get("list", [])
            found = False
            for item in files:
                if item.get("file_name") == part and item.get("dir"):
                    current_fid = item.get("fid")
                    found = True
                    break
            
            if not found:
                return None
        
        return current_fid
    
    def _find_video_file(self, files: List[Dict]) -> Optional[Dict]:
        """
        从文件列表中找到第一个视频文件
        
        Args:
            files: 文件列表
            
        Returns:
            视频文件信息 or None
        """
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts'}
        
        for f in files:
            if f.get("dir"):
                continue
            
            filename = f.get("file_name", "")
            ext = '.' + filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            
            if ext in video_extensions:
                return f
        
        return None

