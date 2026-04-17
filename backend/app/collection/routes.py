"""
Collection API 路由

RESTful 规范：
- 使用名词复数形式 /collections
- 创建：POST /collections
- 查询列表：GET /collections
- 获取单个：GET /collections/{id}
- 更新：PUT /collections/{id}
- 删除：DELETE /collections/{id}
- 操作：POST /collections/{id}/{operation}
"""
import json
import uuid
from typing import Optional
from fastapi import APIRouter, Body, Depends, Query, Path, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..api.schemas.common import (
    ApiResponse,
    build_pagination,
    build_cursor_pagination,
    encode_cursor,
    decode_cursor,
    business_error,
    ok,
    ErrorDetail,
)
from ..api.schemas.sse import create_sse_event
from ..api.sse import stream_with_heartbeat
from ..core.error_codes import ErrorCode
from ..core.auth import verify_api_key

ALLOWED_SORT_FIELDS = frozenset(["saved_at", "title", "year", "status", "id"])


def validate_sort_field(sort_by: str) -> str:
    """验证排序字段是否在白名单中"""
    if sort_by not in ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"无效的排序字段: {sort_by}。允许的字段: {', '.join(sorted(ALLOWED_SORT_FIELDS))}"
        )
    return sort_by


from ..db.session import get_db
from ..core.config import get_settings, Settings
from ..quark.core.transfer_client import QuarkTransferClient
from .schemas import (
    CollectionAddRequest,
    CollectionAddData,
    CollectionListData,
    CollectionListCursorData,
    CollectionDeleteData,
    CollectionItem,
    CollectionCheckLinksRequest,
    CollectionCheckLinksData,
    CollectionVerifyRequest,
    CollectionVerifySingleData,
    CollectionVerifyResult,
    CollectionBatchAddRequest,
    CollectionBatchAddData,
    CollectionBatchAddResult,
    CollectionBatchDeleteRequest,
    CollectionBatchDeleteData,
    CollectionBatchDeleteResult,
)
from .service import CollectionService
from .verify_service import CollectionVerifyService

router = APIRouter(prefix="/collections", tags=["collections"])


def stream_config_error(message: str, request_id: str) -> StreamingResponse:
    async def event_stream():
        error_event = create_sse_event(
            event_type="error",
            data={
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": message,
            },
            message=message,
            level="error",
            code=ErrorCode.CONFIG_ERROR,
            request_id=request_id,
        )
        yield f"data: {json.dumps(error_event.model_dump(), ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post("", response_model=ApiResponse[CollectionAddData], summary="添加收藏")
def add_collection(
    request: CollectionAddRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """
    添加收藏
    
    - **tmdb_id**: TMDB ID
    - **media_type**: 媒体类型 (movie 或 tv)
    - **title**: 标题
    - **share_url**: 夸克分享链接
    """
    service = CollectionService(db)
    success, collection_id, message = service.add(
        tmdb_id=request.tmdb_id,
        media_type=request.media_type,
        title=request.title,
        share_url=request.share_url,
        year=request.year,
        poster_path=request.poster_path,
        backdrop_path=request.backdrop_path,
        share_pwd=request.share_pwd,
        file_structure=request.file_structure,
        category=request.category,
    )
    data = CollectionAddData(created=success, id=collection_id)
    if success:
        return ok(data, message=message)
    if collection_id:
        return business_error(
            data,
            message=message,
            code=ErrorCode.COLLECTION_ALREADY_EXISTS,
            error=ErrorDetail(field="tmdb_id", value=request.tmdb_id, reason="收藏已存在"),
        )
    return business_error(
        data,
        message=message,
        code=ErrorCode.COLLECTION_LINK_INVALID,
        error=ErrorDetail(field="share_url", value=request.share_url, reason=message),
    )


@router.get("", response_model=ApiResponse[CollectionListData], summary="获取收藏列表")
def list_collections(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量（最大100）"),
    sort_by: str = Query("saved_at", description="排序字段"),
    order: str = Query("desc", description="排序方向：asc 或 desc"),
    category: Optional[str] = Query(None, description="分类过滤"),
    status: Optional[int] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
):
    """
    获取收藏列表（传统页码分页）

    支持分页、排序和过滤。适用于中小数据量场景。
    注意：page_size 最大限制为 100
    """
    validate_sort_field(sort_by)
    limit = min(limit, 100)

    service = CollectionService(db)
    total, items = service.list(
        page=page,
        limit=limit,
        sort_by=sort_by,
        order=order,
        category=category,
        status=status,
    )

    # 转换为响应模型
    item_list = [CollectionItem.model_validate(item) for item in items]

    return ok(
        CollectionListData(
            items=item_list,
            pagination=build_pagination(page=page, page_size=limit, total=total),
        )
    )


@router.get("/cursor", response_model=ApiResponse[CollectionListCursorData], summary="获取收藏列表（游标分页）")
def list_collections_cursor(
    cursor: Optional[str] = Query(None, description="游标（用于分页定位）"),
    limit: int = Query(20, ge=1, le=100, description="每页数量（最大100）"),
    sort_by: str = Query("saved_at", description="排序字段"),
    order: str = Query("desc", description="排序方向：asc 或 desc"),
    category: Optional[str] = Query(None, description="分类过滤"),
    status: Optional[int] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
):
    """
    获取收藏列表（游标分页）

    适用于大数据量场景，避免深度分页性能问题。
    使用游标进行分页定位，不支持跳转到指定页码。
    注意：limit 最大限制为 100
    """
    validate_sort_field(sort_by)
    limit = min(limit, 100)

    service = CollectionService(db)
    items, has_more, next_cursor, prev_cursor = service.list_cursor(
        cursor=cursor,
        limit=limit,
        sort_by=sort_by,
        order=order,
        category=category,
        status=status,
    )

    # 转换为响应模型
    item_list = [CollectionItem.model_validate(item) for item in items]

    return ok(
        CollectionListCursorData(
            items=item_list,
            pagination=build_cursor_pagination(
                limit=limit,
                has_more=has_more,
                next_cursor=next_cursor,
                prev_cursor=prev_cursor,
            ),
        )
    )


@router.get("/{collection_id}", response_model=ApiResponse[CollectionItem], summary="获取单个收藏")
def get_collection(
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
):
    """
    获取指定收藏的详细信息
    """
    service = CollectionService(db)
    item = service.get_by_id(collection_id)
    if not item:
        return business_error(
            None,
            message="收藏不存在",
            code=ErrorCode.COLLECTION_NOT_FOUND,
            error=ErrorDetail(field="collection_id", value=collection_id),
        )
    return ok(CollectionItem.model_validate(item))



@router.delete("/{collection_id}", response_model=ApiResponse[CollectionDeleteData], summary="删除收藏")
def delete_collection(
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """
    删除指定的收藏
    """
    service = CollectionService(db)
    success, message = service.delete(collection_id)
    data = CollectionDeleteData(deleted=success)
    if success:
        return ok(data, message=message)
    if "不存在" in message:
        return business_error(
            data,
            message=message,
            code=ErrorCode.COLLECTION_NOT_FOUND,
            error=ErrorDetail(field="collection_id", value=collection_id),
        )
    return business_error(
        data,
        message=message,
        code=ErrorCode.OPERATION_FAILED,
        error=ErrorDetail(field="collection_id", value=collection_id, reason=message),
    )


@router.post("/by-links/check", response_model=ApiResponse[CollectionCheckLinksData], summary="批量检查链接收藏状态")
def check_links_collection(
    request: CollectionCheckLinksRequest,
    db: Session = Depends(get_db),
):
    """
    批量检查多个分享链接的收藏状态
    
    返回每个链接的收藏状态、收藏 ID 和转存状态
    """
    service = CollectionService(db)
    results = service.check_by_links(request.links)
    return ok(
        CollectionCheckLinksData(
            results=[
                {
                    "link": r["link"],
                    "collected": r["collected"],
                    "id": r["id"],
                    "status": r["status"],
                }
                for r in results
            ]
        )
    )


@router.post("/verify", summary="验证收藏网盘状态（SSE）")
async def verify_collections(
    request: Optional[CollectionVerifyRequest] = Body(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    """
    验证收藏对应网盘目录是否存在，并同步修正收藏状态。
    """
    request_id = str(uuid.uuid4())
    if not settings.quark_transfer_cookie:
        return stream_config_error("未配置 QUARK_TRANSFER_COOKIE，无法验证收藏", request_id)

    client = QuarkTransferClient(settings.quark_transfer_cookie or "")
    service = CollectionVerifyService(db, client)
    collection_ids = (request.collection_ids if request else None)

    async def raw_event_stream():
        try:
            async for event in service.verify_all(collection_ids=collection_ids):
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
                    "message": f"验证流异常: {str(e)}",
                },
                message=f"验证流异常: {str(e)}",
                level="error",
                code=500,
                request_id=request_id
            )
            yield f"data: {json.dumps(error_event.model_dump(), ensure_ascii=False)}\n\n"
        finally:
            await client.close()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        stream_with_heartbeat(raw_event_stream()),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post(
    "/verify/{collection_id}",
    response_model=ApiResponse[CollectionVerifySingleData],
    summary="验证单个收藏网盘状态",
)
async def verify_single_collection(
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    _: None = Depends(verify_api_key),
):
    if not settings.quark_transfer_cookie:
        return business_error(
            None,
            message="未配置 QUARK_TRANSFER_COOKIE，无法验证收藏",
            code=ErrorCode.CONFIG_ERROR,
            error=ErrorDetail(field="QUARK_TRANSFER_COOKIE", reason="missing runtime configuration"),
        )

    client = QuarkTransferClient(settings.quark_transfer_cookie or "")
    service = CollectionVerifyService(db, client)
    try:
        result = await service.verify_single(collection_id)
        return ok(
            CollectionVerifySingleData(
                result=CollectionVerifyResult(**result),
            )
        )
    except ValueError as e:
        return business_error(
            None,
            message=str(e),
            code=ErrorCode.COLLECTION_NOT_FOUND,
            error=ErrorDetail(field="collection_id", value=collection_id, reason=str(e)),
        )
    finally:
        await client.close()


# ==================== Batch Operations ====================

@router.post("/batch", response_model=ApiResponse[CollectionBatchAddData], summary="批量添加收藏")
def batch_add_collections(
    request: CollectionBatchAddRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """
    批量添加收藏

    - **items**: 收藏列表，最多50个
    - 返回每个收藏的处理结果
    """
    service = CollectionService(db)
    results = []
    success_count = 0
    failed_count = 0

    for index, item in enumerate(request.items):
        success, collection_id, message = service.add(
            tmdb_id=item.tmdb_id,
            media_type=item.media_type,
            title=item.title,
            share_url=item.share_url,
            year=item.year,
            poster_path=item.poster_path,
            backdrop_path=item.backdrop_path,
            share_pwd=item.share_pwd,
            file_structure=item.file_structure,
            category=item.category,
        )

        result = CollectionBatchAddResult(
            index=index,
            success=success,
            id=collection_id,
            message=message,
        )
        results.append(result)

        if success:
            success_count += 1
        else:
            failed_count += 1

    return ok(
        CollectionBatchAddData(
            total=len(request.items),
            success_count=success_count,
            failed_count=failed_count,
            results=results,
        ),
        message=f"批量添加完成: 成功 {success_count}, 失败 {failed_count}",
    )


@router.delete("/batch", response_model=ApiResponse[CollectionBatchDeleteData], summary="批量删除收藏")
def batch_delete_collections(
    request: CollectionBatchDeleteRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """
    批量删除收藏

    - **ids**: 收藏ID列表，最多100个
    - 返回每个删除操作的结果
    """
    service = CollectionService(db)
    results = []
    success_count = 0
    failed_count = 0

    for collection_id in request.ids:
        success, message = service.delete(collection_id)

        result = CollectionBatchDeleteResult(
            id=collection_id,
            success=success,
            message=message,
        )
        results.append(result)

        if success:
            success_count += 1
        else:
            failed_count += 1

    return ok(
        CollectionBatchDeleteData(
            total=len(request.ids),
            success_count=success_count,
            failed_count=failed_count,
            results=results,
        ),
        message=f"批量删除完成: 成功 {success_count}, 失败 {failed_count}",
    )


@router.post("/batch/sse", summary="批量添加收藏（SSE进度反馈）")
async def batch_add_collections_sse(
    request: CollectionBatchAddRequest,
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """
    批量添加收藏（带SSE进度反馈）

    - **items**: 收藏列表，最多50个
    - 通过SSE返回每个收藏的处理进度
    """
    service = CollectionService(db)
    request_id = str(uuid.uuid4())

    async def event_stream():
        total = len(request.items)
        success_count = 0
        failed_count = 0

        for index, item in enumerate(request.items):
            try:
                success, collection_id, message = service.add(
                    tmdb_id=item.tmdb_id,
                    media_type=item.media_type,
                    title=item.title,
                    share_url=item.share_url,
                    year=item.year,
                    poster_path=item.poster_path,
                    backdrop_path=item.backdrop_path,
                    share_pwd=item.share_pwd,
                    file_structure=item.file_structure,
                    category=item.category,
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
                            "index": index,
                            "title": item.title,
                            "success": success,
                            "id": collection_id,
                        },
                    },
                    message=f"处理 {item.title}: {'成功' if success else '失败'}",
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
                    },
                    message=f"处理 {item.title} 时出错: {str(e)}",
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
            message=f"批量添加完成: 成功 {success_count}, 失败 {failed_count}",
            level="info",
            request_id=request_id,
        )
        yield f"data: {json.dumps(complete_event.model_dump(), ensure_ascii=False)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
