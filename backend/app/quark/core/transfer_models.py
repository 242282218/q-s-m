"""
夸克转存数据模型
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ShareInfo:
    """
    分享信息
    """
    pwd_id: str
    stoken: str
    title: str
    total_files: int = 0


@dataclass
class FileDetail:
    """
    文件详情
    """
    fid: str
    title: str
    file_type: int = 1  # 1: 文件, 2: 目录
    size: int = 0
    pdir_fid: str = "0"
    share_fid_token: str = ""


@dataclass
class TaskStatus:
    """
    任务状态
    """
    task_id: str
    status: int  # 0: 未开始, 1: 进行中, 2: 已完成, 3: 失败
    message: str
    progress: int = 0
    
    @property
    def is_success(self) -> bool:
        """
        是否成功
        """
        return self.status == 2
    
    @property
    def is_failed(self) -> bool:
        """
        是否失败
        """
        return self.status == 3


@dataclass
class TransferResult:
    """
    转存结果
    """
    success: bool
    task_id: str = ""
    message: str = ""
    saved_files: List[str] = field(default_factory=list)
