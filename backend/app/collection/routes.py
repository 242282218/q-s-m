"""
Collection API 路由
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session

from ..db.session import get_db
from .schemas import (
    CollectionAddRequest,
    CollectionAddResponse,
    CollectionListResponse,
    CollectionCheckResponse,
    CollectionDeleteResponse,
    CollectionItem,
)
from .service import CollectionService

router = APIRouter(prefix="/collection", tags=["collection"])


@router.post("/add", response_model=CollectionAddResponse, summary="添加收藏")
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
    success, id, message = service.add(
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
    return CollectionAddResponse(success=success, id=id, message=message)


@router.get("/list", response_model=CollectionListResponse, summary="获取收藏列表")
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
    
    return CollectionListResponse(
        total=total,
        page=page,
        limit=limit,
        items=item_list,
    )


@router.get("/check/{tmdb_id}", response_model=CollectionCheckResponse, summary="检查是否已收藏")
def check_collection(
    tmdb_id: int = Path(..., description="TMDB ID"),
    media_type: str = Query("movie", description="媒体类型"),
    db: Session = Depends(get_db),
):
    """
    检查指定 TMDB ID 是否已收藏
    """
    service = CollectionService(db)
    collected, id = service.check(tmdb_id, media_type)
    return CollectionCheckResponse(collected=collected, id=id)


@router.delete("/{collection_id}", response_model=CollectionDeleteResponse, summary="删除收藏")
def delete_collection(
    collection_id: int = Path(..., description="收藏 ID"),
    db: Session = Depends(get_db),
):
    """
    删除指定的收藏
    """
    service = CollectionService(db)
    success, message = service.delete(collection_id)
    return CollectionDeleteResponse(success=success, message=message)
