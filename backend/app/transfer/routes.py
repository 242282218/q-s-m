"""
Transfer API 路由
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..api.schemas.common import ApiResponse, business_error, ok
from ..db.session import get_db
from ..core.config import get_settings, Settings
from .service import TransferService


router = APIRouter(prefix="/transfer", tags=["transfer"])


class ValidateLinkRequest(BaseModel):
    """验证链接请求"""
    share_url: str


class TransferFile(BaseModel):
    fid: str | None = None
    name: str | None = None
    size: int = 0
    is_dir: bool = False


class ValidateLinkData(BaseModel):
    """验证链接数据"""
    valid: bool
    files: list[TransferFile] = Field(default_factory=list)


class TransferExecRequest(BaseModel):
    """执行转存请求"""
    collection_id: int
    target_folder: Optional[str] = None
    auto_rename: bool = False


class RenameRequest(BaseModel):
    """独立重命名请求"""
    collection_id: int


class TransferredFile(BaseModel):
    fid: str | None = None
    name: str | None = None
    size: int | None = None
    path: str | None = None


class TransferExecData(BaseModel):
    """执行转存数据"""
    success: bool
    files: list[TransferredFile] = Field(default_factory=list)


@router.post("/validate", response_model=ApiResponse[ValidateLinkData], summary="验证分享链接")
async def validate_link(
    request: ValidateLinkRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    验证夸克分享链接是否有效
    
    返回链接中的文件列表
    """
    service = TransferService(db, cookie=settings.quark_transfer_cookie or "")
    try:
        valid, message, files = await service.validate_link(request.share_url)
        payload = ValidateLinkData(
            valid=valid,
            files=[TransferFile.model_validate(item) for item in files],
        )
        if valid:
            return ok(payload, message=message)
        return business_error(payload, message=message, code=1)
    finally:
        await service.close()


@router.post("/exec", response_model=ApiResponse[TransferExecData], summary="执行转存")
async def transfer_exec(
    request: TransferExecRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    执行转存操作
    
    - **collection_id**: 收藏 ID
    - **target_folder**: 目标目录 (可选，默认根据分类自动确定)
    - **auto_rename**: 是否自动重命名 (默认 False)
    """
    service = TransferService(db, cookie=settings.quark_transfer_cookie or "")
    try:
        success, message, files = await service.transfer_collection(
            collection_id=request.collection_id,
            target_folder=request.target_folder,
            auto_rename=request.auto_rename,
        )
        payload = TransferExecData(
            success=success,
            files=[TransferredFile.model_validate(item) for item in files],
        )
        if success:
            return ok(payload, message=message)
        return business_error(payload, message=message, code=1)
    finally:
        await service.close()


@router.post("/rename", summary="独立重命名（SSE）")
async def rename_collection(
    request: RenameRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    service = TransferService(db, cookie=settings.quark_transfer_cookie or "")

    def wrap_event(event: dict, code: int = 0) -> dict:
        return {
            "code": code,
            "message": event.get("message", ""),
            "data": event,
        }

    async def event_stream():
        try:
            async for event in service.rename_collection(request.collection_id):
                yield f"data: {json.dumps(wrap_event(event), ensure_ascii=False)}\n\n"
        except Exception as e:
            error_event = {
                "type": "error",
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": f"重命名流异常: {str(e)}",
                "level": "error",
            }
            yield f"data: {json.dumps(wrap_event(error_event, code=500), ensure_ascii=False)}\n\n"
        finally:
            await service.close()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
