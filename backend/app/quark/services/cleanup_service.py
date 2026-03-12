"""
清理服务
负责清理非视频文件和空目录
"""
import logging
from typing import AsyncGenerator, Dict, Any, Set

from app.quark.core.transfer_client import QuarkTransferClient
from app.transfer.renamer import Renamer
from app.transfer.emby import cleanup_non_video_files
from app.core.exceptions import CleanupException
from app.core.error_codes import ErrorCode

logger = logging.getLogger(__name__)


class CleanupService:
    """清理服务"""

    def __init__(self, renamer: Renamer):
        self.renamer = renamer

    async def cleanup_files(
        self,
        client: QuarkTransferClient,
        root_fid: str,
        protected_video_fids: Set[str],
        keep_subtitles: bool = False,
        dry_run: bool = False,
        delete_non_video: bool = True,
        delete_unselected_videos: bool = True,
        delete_empty_dirs: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        清理非视频文件

        Args:
            client: 夸克客户端
            root_fid: 根目录 FID
            protected_video_fids: 受保护的视频文件 FID 集合
            keep_subtitles: 是否保留字幕
            dry_run: 是否为演练模式
            delete_non_video: 是否删除非视频文件
            delete_unselected_videos: 是否删除未选中的视频
            delete_empty_dirs: 是否删除空目录

        Yields:
            清理事件
        """
        try:
            async for event in cleanup_non_video_files(
                client=client,
                root_fid=root_fid,
                renamer=self.renamer,
                protected_video_fids=protected_video_fids,
                keep_subtitles=keep_subtitles,
                dry_run=dry_run,
                delete_non_video=delete_non_video,
                delete_unselected_videos=delete_unselected_videos,
                delete_empty_dirs=delete_empty_dirs,
            ):
                yield event

        except Exception as e:
            logger.error(f"清理失败: {e}", exc_info=True)
            raise CleanupException(f"清理失败: {str(e)}", code=ErrorCode.OPERATION_FAILED)
