"""
Transfer API 路由
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..db.session import get_db
from .service import TransferService


router = APIRouter(prefix="/transfer", tags=["transfer"])


class ValidateLinkRequest(BaseModel):
    """验证链接请求"""
    share_url: str


class ValidateLinkResponse(BaseModel):
    """验证链接响应"""
    valid: bool
    message: str
    files: list = []


class TransferExecRequest(BaseModel):
    """执行转存请求"""
    collection_id: int
    target_folder: Optional[str] = None
    auto_rename: bool = True


class TransferExecResponse(BaseModel):
    """执行转存响应"""
    success: bool
    message: str
    files: list = []


@router.post("/validate", response_model=ValidateLinkResponse, summary="验证分享链接")
async def validate_link(
    request: ValidateLinkRequest,
    db: Session = Depends(get_db),
):
    """
    验证夸克分享链接是否有效
    
    返回链接中的文件列表
    """
    service = TransferService(db)
    try:
        valid, message, files = await service.validate_link(request.share_url)
        return ValidateLinkResponse(valid=valid, message=message, files=files)
    finally:
        await service.close()


@router.post("/exec", response_model=TransferExecResponse, summary="执行转存")
async def transfer_exec(
    request: TransferExecRequest,
    db: Session = Depends(get_db),
):
    """
    执行转存操作
    
    - **collection_id**: 收藏 ID
    - **target_folder**: 目标目录 (可选，默认根据分类自动确定)
    - **auto_rename**: 是否自动重命名 (默认 True)
    """
    service = TransferService(db)
    try:
        success, message, files = await service.transfer_collection(
            collection_id=request.collection_id,
            target_folder=request.target_folder,
            auto_rename=request.auto_rename,
        )
        return TransferExecResponse(success=success, message=message, files=files)
    finally:
        await service.close()
