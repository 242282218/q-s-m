"""
Collection API 路由
"""
import json
from typing import Optional
from fastapi import APIRouter, Body, Depends, Query, Path, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..api.schemas.common import ApiResponse, build_pagination, business_error, ok
from ..db.session import get_db
from ..core.config import get_settings, Settings
from ..quark.core.transfer_client import QuarkTransferClient
from .schemas import (
    CollectionAddRequest,
    CollectionAddData,
    CollectionListData,
    CollectionCheckData,
    CollectionDeleteData,
    CollectionItem,
    CollectionCheckLinkData,
    CollectionCheckLinksRequest,
    CollectionCheckLinksData,
    CollectionVerifyRequest,
    CollectionVerifySingleData,
    CollectionVerifyResult,
)
from .service import CollectionService
from .verify_service import CollectionVerifyService

router = APIRouter(prefix="/collection", tags=["collection"])


@router.post("/add", response_model=ApiResponse[CollectionAddData], summary="添加收藏")
def add_collection(
    request: CollectionAddRequest,
    db: Session = Depends(get_db),
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
        return business_error(data, message=message, code=409)
    return business_error(data, message=message, code=1)


@router.get("/list", response_model=ApiResponse[CollectionListData], summary="获取收藏列表")
def list_collections(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: str = Query("saved_at", description="排序字段"),
    order: str = Query("desc", description="排序方向: asc 或 desc"),
    category: Optional[str] = Query(None, description="分类过滤"),
    status: Optional[int] = Query(None, description="状态过滤"),
    db: Session = Depends(get_db),
):
    """
    获取收藏列表
    
    支持分页、排序和过滤
    """
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


@router.get("/check/{tmdb_id}", response_model=ApiResponse[CollectionCheckData], summary="检查是否已收藏")
def check_collection(
    tmdb_id: int = Path(..., description="TMDB ID"),
    media_type: str = Query("movie", description="媒体类型"),
    db: Session = Depends(get_db),
):
    """
    检查指定 TMDB ID 是否已收藏
    """
    service = CollectionService(db)
    collected, collection_id = service.check(tmdb_id, media_type)
    return ok(CollectionCheckData(collected=collected, id=collection_id))


@router.delete("/{collection_id}", response_model=ApiResponse[CollectionDeleteData], summary="删除收藏")
def delete_collection(
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
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
        return business_error(data, message=message, code=404)
    return business_error(data, message=message, code=1)


@router.get("/check-link", response_model=ApiResponse[CollectionCheckLinkData], summary="检查链接是否已收藏")
def check_link_collection(
    link: str = Query(..., description="分享链接"),
    db: Session = Depends(get_db),
):
    """
    检查指定分享链接是否已收藏
    
    返回收藏状态和收藏 ID、状态
    """
    service = CollectionService(db)
    collected, collection_id, status = service.check_by_link(link)
    return ok(CollectionCheckLinkData(collected=collected, id=collection_id, status=status))


@router.post("/check-links", response_model=ApiResponse[CollectionCheckLinksData], summary="批量检查链接收藏状态")
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
):
    """
    验证收藏对应网盘目录是否存在，并同步修正收藏状态。
    """
    client = QuarkTransferClient(settings.quark_transfer_cookie or "")
    service = CollectionVerifyService(db, client)
    collection_ids = (request.collection_ids if request else None)

    def wrap_event(event: dict, code: int = 0) -> dict:
        return {
            "code": code,
            "message": event.get("message", ""),
            "data": event,
        }

    async def event_stream():
        try:
            async for event in service.verify_all(collection_ids=collection_ids):
                yield f"data: {json.dumps(wrap_event(event), ensure_ascii=False)}\n\n"
        except Exception as e:
            error_event = {
                "type": "error",
                "current": 0,
                "total": 0,
                "percentage": 0,
                "message": f"验证流异常: {str(e)}",
                "level": "error",
            }
            yield f"data: {json.dumps(wrap_event(error_event, code=500), ensure_ascii=False)}\n\n"
        finally:
            await client.close()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@router.post(
    "/verify/{collection_id}",
    response_model=ApiResponse[CollectionVerifySingleData],
    summary="验证单个收藏网盘状态",
)
async def verify_single_collection(
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
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
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        await client.close()
