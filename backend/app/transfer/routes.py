"""
Transfer API 路由

RESTful 规范：
- 使用名词复数形式 /transfers/{id}
- 操作使用 POST /transfers/{id}/execute
- 重命名使用 POST /transfers/{id}/rename
- 批量操作使用 POST /transfers/batch
"""
import json
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Path
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, ConfigDict

from ..api.schemas.common import ApiResponse, business_error, ok, ErrorDetail
from ..api.schemas.sse import create_sse_event
from ..core.error_codes import ErrorCode
from ..core.auth import verify_api_key
from ..db.session import get_db
from ..core.config import get_settings, Settings
from .service import TransferService


router = APIRouter(prefix="/transfers", tags=["transfers"])


def build_transfer_exec_error_detail(
    message: str,
    collection_id: int,
    target_folder: Optional[str],
) -> tuple[ErrorCode, ErrorDetail]:
    if "收藏不存在" in message:
        return (
            ErrorCode.COLLECTION_NOT_FOUND,
            ErrorDetail(field="collection_id", value=collection_id, reason=message),
        )

    if "未配置 QUARK_TRANSFER_COOKIE" in message:
        return (
            ErrorCode.CONFIG_ERROR,
            ErrorDetail(field="QUARK_TRANSFER_COOKIE", reason="missing runtime configuration"),
        )

    if "未配置 TMDB_API_KEY" in message:
        return (
            ErrorCode.CONFIG_ERROR,
            ErrorDetail(field="TMDB_API_KEY", reason="missing runtime configuration"),
        )

    if "转存超时" in message:
        return (
            ErrorCode.TRANSFER_TIMEOUT,
            ErrorDetail(field="collection_id", value=collection_id, reason=message),
        )

    if "创建目标目录失败" in message:
        failed_target = message.partition(":")[2].strip() or target_folder
        return (
            ErrorCode.TRANSFER_DIR_NOT_FOUND,
            ErrorDetail(field="target_folder", value=failed_target, reason=message),
        )

    if "没有可转存的文件" in message or "没有文件" in message:
        return (
            ErrorCode.TRANSFER_NO_FILES,
            ErrorDetail(field="collection_id", value=collection_id, reason=message),
        )

    return (
        ErrorCode.TRANSFER_FAILED,
        ErrorDetail(field="collection_id", value=collection_id, reason=message),
    )


class ValidateLinkRequest(BaseModel):
    """验证链接请求"""
    model_config = ConfigDict(defer_build=True)

    share_url: str


class TransferFile(BaseModel):
    """转存文件信息"""
    model_config = ConfigDict(defer_build=True)

    fid: str | None = None
    name: str | None = None
    size: int = 0
    is_dir: bool = False


class ValidateLinkData(BaseModel):
    """验证链接数据"""
    model_config = ConfigDict(defer_build=True)

    valid: bool
    files: list[TransferFile] = Field(default_factory=list)


class TransferExecRequest(BaseModel):
    """执行转存请求"""
    model_config = ConfigDict(defer_build=True)

    target_folder: Optional[str] = None
    auto_rename: bool = False


class TransferredFile(BaseModel):
    """已转存文件信息"""
    model_config = ConfigDict(defer_build=True)

    fid: str | None = None
    name: str | None = None
    size: int | None = None
    path: str | None = None


class TransferExecData(BaseModel):
    """执行转存数据"""
    model_config = ConfigDict(defer_build=True)

    success: bool
    files: list[TransferredFile] = Field(default_factory=list)


# ==================== Batch Operation Schemas ====================

class TransferBatchItem(BaseModel):
    """批量转存单项"""
    model_config = ConfigDict(defer_build=True)

    collection_id: int = Field(..., description="收藏ID")
    target_folder: Optional[str] = Field(None, description="目标目录")
    auto_rename: bool = Field(False, description="是否自动重命名")


class TransferBatchRequest(BaseModel):
    """批量转存请求"""
    model_config = ConfigDict(defer_build=True)

    items: List[TransferBatchItem] = Field(..., description="转存列表", max_length=20)


class TransferBatchResult(BaseModel):
    """批量转存结果项"""
    model_config = ConfigDict(defer_build=True)

    collection_id: int
    success: bool
    message: str = ""
    files: list[TransferredFile] = Field(default_factory=list)


class TransferBatchData(BaseModel):
    """批量转存响应数据"""
    model_config = ConfigDict(defer_build=True)

    total: int
    success_count: int
    failed_count: int
    results: List[TransferBatchResult]


@router.post("/validate", response_model=ApiResponse[ValidateLinkData], summary="验证分享链接")
async def validate_link(
    request: ValidateLinkRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    """
    验证夸克分享链接是否有效
    
    返回链接中的文件列表
    """
    if not settings.quark_transfer_cookie:
        payload = ValidateLinkData(valid=False, files=[])
        return business_error(
            payload,
            message="未配置 QUARK_TRANSFER_COOKIE，无法验证分享链接",
            code=ErrorCode.CONFIG_ERROR,
            error=ErrorDetail(field="QUARK_TRANSFER_COOKIE", reason="missing runtime configuration"),
        )

    service = TransferService(db, cookie=settings.quark_transfer_cookie)
    try:
        valid, message, files = await service.validate_link(request.share_url)
        payload = ValidateLinkData(
            valid=valid,
            files=[TransferFile.model_validate(item) for item in files],
        )
        if valid:
            return ok(payload, message=message)
        return business_error(
            payload,
            message=message,
            code=ErrorCode.COLLECTION_LINK_INVALID,
            error=ErrorDetail(field="share_url", value=request.share_url, reason="链接无效或已过期"),
        )
    finally:
        await service.close()


@router.post("/{collection_id}/execute", response_model=ApiResponse[TransferExecData], summary="执行转存")
async def transfer_exec(
    request: Request,
    body: TransferExecRequest,
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    """
    执行转存操作
    
    - **collection_id**: 收藏 ID（从路径参数获取）
    - **target_folder**: 目标目录 (可选，默认根据分类自动确定)
    - **auto_rename**: 是否自动重命名 (默认 False)
    """
    tmdb_client = getattr(request.app.state, "tmdb_client", None)
    service = TransferService(db, cookie=settings.quark_transfer_cookie or "", tmdb_client=tmdb_client)
    try:
        success, message, files = await service.transfer_collection(
            collection_id=collection_id,
            target_folder=body.target_folder,
            auto_rename=body.auto_rename,
        )
        payload = TransferExecData(
            success=success,
            files=[TransferredFile.model_validate(item) for item in files],
        )
        if success:
            return ok(payload, message=message)
        code, error = build_transfer_exec_error_detail(message, collection_id, body.target_folder)
        return business_error(
            payload,
            message=message,
            code=code,
            error=error,
        )
    finally:
        await service.close()


@router.post("/{collection_id}/rename", summary="独立重命名（SSE）")
async def rename_collection(
    request: Request,
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    """
    对指定收藏执行重命名操作（SSE 流式响应）
    
    - **collection_id**: 收藏 ID
    
    返回重命名进度事件流
    """
    tmdb_client = getattr(request.app.state, "tmdb_client", None)
    service = TransferService(db, cookie=settings.quark_transfer_cookie or "", tmdb_client=tmdb_client)
    request_id = str(uuid.uuid4())

    async def event_stream():
        try:
            async for event in service.rename_collection(collection_id):
                sse_event = create_sse_event(
                    event_type=event.get("type", "log"),
                    data=event,
                    message=event.get("message", ""),
                    level=event.get("level", "info"),
                    request_id=request_id
                )
                yield f"data: {json.dumps(sse_event.model_dump(), ensure_ascii=False)}\n\n"
        except Exception as e:
            error_event = create_sse_event(
                event_type="error",
                data={
                    "current": 0,
                    "total": 0,
                    "percentage": 0,
                    "message": f"重命名流异常：{str(e)}",
                },
                message=f"重命名流异常：{str(e)}",
                level="error",
                code=ErrorCode.RENAME_FAILED,
                request_id=request_id
            )
            yield f"data: {json.dumps(error_event.model_dump(), ensure_ascii=False)}\n\n"
        finally:
            await service.close()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("/batch", response_model=ApiResponse[TransferBatchData], summary="批量转存")
async def batch_transfer(
    request: Request,
    body: TransferBatchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    """
    批量转存操作

    - **items**: 转存列表，最多20个
    - 返回每个转存操作的结果
    """
    tmdb_client = getattr(request.app.state, "tmdb_client", None)
    service = TransferService(db, cookie=settings.quark_transfer_cookie or "", tmdb_client=tmdb_client)
    try:
        results = []
        success_count = 0
        failed_count = 0

        for item in body.items:
            success, message, files = await service.transfer_collection(
                collection_id=item.collection_id,
                target_folder=item.target_folder,
                auto_rename=item.auto_rename,
            )

            result = TransferBatchResult(
                collection_id=item.collection_id,
                success=success,
                message=message,
                files=[TransferredFile.model_validate(f) for f in files],
            )
            results.append(result)

            if success:
                success_count += 1
            else:
                failed_count += 1

        return ok(
            TransferBatchData(
                total=len(body.items),
                success_count=success_count,
                failed_count=failed_count,
                results=results,
            ),
            message=f"批量转存完成: 成功 {success_count}, 失败 {failed_count}",
        )
    finally:
        await service.close()


@router.post("/batch/sse", summary="批量转存（SSE进度反馈）")
async def batch_transfer_sse(
    request: Request,
    body: TransferBatchRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    """
    批量转存操作（带SSE进度反馈）

    - **items**: 转存列表，最多20个
    - 通过SSE返回每个转存的处理进度
    """
    tmdb_client = getattr(request.app.state, "tmdb_client", None)
    request_id = str(uuid.uuid4())

    async def event_stream():
        service = TransferService(db, cookie=settings.quark_transfer_cookie or "", tmdb_client=tmdb_client)
        try:
            total = len(body.items)
            success_count = 0
            failed_count = 0

            for index, item in enumerate(body.items):
                try:
                    success, message, files = await service.transfer_collection(
                        collection_id=item.collection_id,
                        target_folder=item.target_folder,
                        auto_rename=item.auto_rename,
                    )

                    if success:
                        success_count += 1
                    else:
                        failed_count += 1

                    progress_event = create_sse_event(
                        event_type="progress",
                        data={
                            "current": index + 1,
                            "total": total,
                            "percentage": round((index + 1) / total * 100, 1),
                            "success_count": success_count,
                            "failed_count": failed_count,
                            "current_item": {
                                "collection_id": item.collection_id,
                                "success": success,
                                "files_count": len(files),
                            },
                        },
                        message=f"转存收藏 {item.collection_id}: {'成功' if success else '失败'}",
                        level="info" if success else "warning",
                        request_id=request_id,
                    )
                    yield f"data: {json.dumps(progress_event.model_dump(), ensure_ascii=False)}\n\n"

                except Exception as e:
                    failed_count += 1
                    error_event = create_sse_event(
                        event_type="error",
                        data={
                            "current": index + 1,
                            "total": total,
                            "percentage": round((index + 1) / total * 100, 1),
                            "success_count": success_count,
                            "failed_count": failed_count,
                            "collection_id": item.collection_id,
                        },
                        message=f"转存收藏 {item.collection_id} 时出错: {str(e)}",
                        level="error",
                        request_id=request_id,
                    )
                    yield f"data: {json.dumps(error_event.model_dump(), ensure_ascii=False)}\n\n"

            # 发送完成事件
            complete_event = create_sse_event(
                event_type="complete",
                data={
                    "total": total,
                    "success_count": success_count,
                    "failed_count": failed_count,
                },
                message=f"批量转存完成: 成功 {success_count}, 失败 {failed_count}",
                level="info",
                request_id=request_id,
            )
            yield f"data: {json.dumps(complete_event.model_dump(), ensure_ascii=False)}\n\n"

        finally:
            await service.close()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)



