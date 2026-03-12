"""
重命名服务
负责文件重命名逻辑
"""
import logging
from typing import AsyncGenerator, Dict, Any, Set

from app.quark.core.transfer_client import QuarkTransferClient
from app.transfer.renamer import Renamer
from app.transfer.emby import reorganize_to_emby_structure, collect_video_files
from app.core.exceptions import RenameException
from app.core.error_codes import ErrorCode

logger = logging.getLogger(__name__)


class RenameService:
    """重命名服务"""

    def __init__(self, renamer: Renamer):
        self.renamer = renamer

    async def rename_media_files(
        self,
        client: QuarkTransferClient,
        root_fid: str,
        root_path: str,
        title: str,
        year: int,
        media_type: str,
        keep_extras: bool = False,
        dry_run: bool = False
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        重命名媒体文件

        Args:
            client: 夸克客户端
            root_fid: 根目录 FID
            root_path: 根目录路径
            title: 标题
            year: 年份
            media_type: 媒体类型
            keep_extras: 是否保留额外内容
            dry_run: 是否为演练模式

        Yields:
            重命名事件
        """
        try:
            # 收集视频文件
            video_files = await collect_video_files(client, root_fid, self.renamer)
            if not video_files:
                yield {
                    "type": "error",
                    "message": "未识别到视频文件",
                    "level": "warning"
                }
                return

            # 重组文件结构
            async for event in reorganize_to_emby_structure(
                client=client,
                root_fid=root_fid,
                root_path=root_path,
                video_files=video_files,
                renamer=self.renamer,
                title=title,
                year=year,
                media_type=media_type,
                keep_extras=keep_extras,
                dry_run=dry_run,
            ):
                yield event

        except Exception as e:
            logger.error(f"重命名失败: {e}", exc_info=True)
            raise RenameException(f"重命名失败: {str(e)}", code=ErrorCode.RENAME_FAILED)

    async def collect_retained_fids(
        self,
        client: QuarkTransferClient,
        root_fid: str,
        root_path: str,
        title: str,
        year: int,
        media_type: str,
        keep_extras: bool = False,
        dry_run: bool = False
    ) -> Set[str]:
        """
        收集重命名后保留的文件 FID

        Returns:
            保留的文件 FID 集合
        """
        retained_fids = set()
        async for event in self.rename_media_files(
            client, root_fid, root_path, title, year, media_type, keep_extras, dry_run
        ):
            if event.get("type") == "complete":
                retained_fids.update(event.get("retained_fids") or [])
        return retained_fids
