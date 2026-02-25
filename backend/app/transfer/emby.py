"""
Emby v1.6 命名与夸克云转存重命名工作流。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

from app.core.config import get_settings
from app.quark.core.transfer_client import QuarkTransferClient
from app.services.tmdb import TmdbClient
from app.transfer.renamer import Renamer
from app.utils.events import build_event_payload

logger = logging.getLogger(__name__)


_RES_4K = re.compile(r"(2160p|4k|uhd)", re.IGNORECASE)
_RES_1080P = re.compile(r"1080p", re.IGNORECASE)
_RES_720P = re.compile(r"720p", re.IGNORECASE)
_RES_LOW = re.compile(r"(576p|540p|480p)", re.IGNORECASE)

_HDR_DV = re.compile(r"(dolby[\s\-]?vision|dv|dovi)", re.IGNORECASE)
_HDR10_PLUS = re.compile(r"(hdr10\+|hdr10plus)", re.IGNORECASE)
_HDR10 = re.compile(r"(hdr|hdr10)", re.IGNORECASE)
_HDR_10BIT = re.compile(r"(10bit|10[\s\-]?bit)", re.IGNORECASE)

_SRC_BLURAY = re.compile(r"(blu[\s\-]?ray|bdrip|bdremux|remux)", re.IGNORECASE)
_SRC_WEB = re.compile(r"(web[\s\-]?(dl|rip)|webrip)", re.IGNORECASE)
_SRC_DVD = re.compile(r"(dvdrip|dvd)", re.IGNORECASE)

_CODEC_H265 = re.compile(r"(x265|h\.?265|hevc|av1)", re.IGNORECASE)
_CODEC_H264 = re.compile(r"(x264|h\.?264|avc)", re.IGNORECASE)


def _get_category_base_dirs() -> Dict[str, str]:
    settings = get_settings()
    return {
        "movie": settings.base_movie_dir,
        "tv": settings.base_tv_dir,
        "anime": settings.base_anime_dir,
        "documentary": settings.base_documentary_dir,
    }


@dataclass
class TmdbNamingInfo:
    tmdb_id: Optional[int]
    media_type: str
    category: str
    title: str
    year: Optional[int]
    season_count: Optional[int]


def get_category_base_dir(category: str) -> str:
    base_dirs = _get_category_base_dirs()
    return base_dirs.get(category, base_dirs["movie"])


def _parse_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return int(date_str[:4])
    except (TypeError, ValueError):
        return None


def _pick_best_search_result(results: List[Dict[str, Any]], year: Optional[int]) -> Optional[Dict[str, Any]]:
    if not results:
        return None
    if year is None:
        return results[0]

    def score(item: Dict[str, Any]) -> Tuple[int, float]:
        item_year = _parse_year(item.get("release_date") or item.get("first_air_date"))
        if item_year is None:
            return (9999, -(item.get("popularity") or 0.0))
        return (abs(item_year - year), -(item.get("popularity") or 0.0))

    return sorted(results, key=score)[0]


def _normalize_compare_text(text: Optional[str]) -> str:
    if not text:
        return ""
    lowered = text.lower()
    return re.sub(r"[\W_]+", "", lowered, flags=re.UNICODE)


def _title_matches_details(query_title: Optional[str], details: Dict[str, Any]) -> bool:
    if not query_title or not details:
        return True

    query_norm = _normalize_compare_text(query_title)
    if not query_norm:
        return True

    candidates = [
        details.get("name"),
        details.get("title"),
        details.get("original_name"),
        details.get("original_title"),
    ]
    for candidate in candidates:
        cand_norm = _normalize_compare_text(candidate)
        if not cand_norm:
            continue
        if query_norm in cand_norm or cand_norm in query_norm:
            return True
    return False


def resolve_media_category(media_type: str, genres: List[Dict[str, Any]]) -> str:
    normalized = (media_type or "").lower()
    if normalized == "anime":
        return "anime"
    if normalized == "movie":
        return "movie"

    genre_ids = {int(g.get("id")) for g in genres if isinstance(g, dict) and g.get("id")}
    if normalized == "tv" and 16 in genre_ids:
        return "anime"
    return "tv"


def pick_romanized_title(alternative_titles: List[Dict[str, Any]], renamer: Renamer) -> Optional[str]:
    candidates: List[Tuple[int, int, str]] = []
    for idx, item in enumerate(alternative_titles or []):
        raw_title = item.get("title") or item.get("name")
        if not raw_title:
            continue

        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", raw_title):
            continue

        cleaned = renamer.sanitize_for_emby(raw_title, ascii_only=True)
        if not cleaned:
            continue

        score = 0
        type_tag = (item.get("type") or "").lower()
        region = (item.get("iso_3166_1") or "").upper()

        if "romaji" in type_tag:
            score += 100
        if "hepburn" in type_tag:
            score += 90
        if region == "JP":
            score += 20
        if region in {"US", "GB", "ES", "MX"}:
            score += 5

        candidates.append((score, -idx, cleaned))

    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][2]


def _extract_tmdb_title(details: Dict[str, Any], normalized_media_type: str) -> Optional[str]:
    if not details:
        return None
    if normalized_media_type == "movie":
        return details.get("title") or details.get("original_title")
    return details.get("name") or details.get("original_name")


async def resolve_tmdb_naming_info(
    tmdb_client: TmdbClient,
    renamer: Renamer,
    *,
    media_type: str,
    tmdb_id: Optional[int] = None,
    title: Optional[str] = None,
    year: Optional[int] = None,
) -> TmdbNamingInfo:
    normalized_media_type = "movie" if (media_type or "").lower() == "movie" else "tv"
    resolved_tmdb_id = tmdb_id
    # 0/None 均视为“未提供有效 tmdb_id”，允许后续走搜索与纠正流程。
    explicit_tmdb_id = bool(tmdb_id)

    if not resolved_tmdb_id and title:
        if normalized_media_type == "movie":
            search_results = await tmdb_client.search_movies(title, year)
        else:
            search_results = await tmdb_client.search_tv(title, year)
        best = _pick_best_search_result(search_results, year)
        if best:
            resolved_tmdb_id = best.get("id")

    details_zh: Dict[str, Any] = {}
    details_en: Dict[str, Any] = {}
    if resolved_tmdb_id:
        details_zh = await tmdb_client.details(normalized_media_type, resolved_tmdb_id, language_override="zh-CN")
        details_en = await tmdb_client.details(normalized_media_type, resolved_tmdb_id, language_override="en-US")

        title_matches = _title_matches_details(title, details_zh) or _title_matches_details(title, details_en)
        if title and not title_matches and not explicit_tmdb_id:
            if normalized_media_type == "movie":
                search_results = await tmdb_client.search_movies(title, year)
            else:
                search_results = await tmdb_client.search_tv(title, year)
            best = _pick_best_search_result(search_results, year)
            best_id = best.get("id") if best else None
            if best_id and best_id != resolved_tmdb_id:
                logger.warning(
                    "TMDB ID 被搜索结果修正: %s -> %s (title=%s, year=%s)",
                    resolved_tmdb_id, best_id, title, year,
                )
                resolved_tmdb_id = best_id
                details_zh = await tmdb_client.details(normalized_media_type, resolved_tmdb_id, language_override="zh-CN")
                details_en = await tmdb_client.details(normalized_media_type, resolved_tmdb_id, language_override="en-US")
        elif title and not title_matches and explicit_tmdb_id:
            logger.warning(
                "resolve_tmdb_naming_info: 调用方提供的 tmdb_id=%s 与标题[%s]不匹配，保留原始 tmdb_id",
                tmdb_id,
                title,
            )

    primary_details = details_zh or details_en
    genres = primary_details.get("genres") or details_en.get("genres") or []
    category = resolve_media_category(media_type, genres)

    resolved_year = (
        _parse_year(primary_details.get("release_date") or primary_details.get("first_air_date"))
        or _parse_year(details_en.get("release_date") or details_en.get("first_air_date"))
        or year
    )
    season_count = (
        (primary_details.get("number_of_seasons") if normalized_media_type == "tv" else None)
        or (details_en.get("number_of_seasons") if normalized_media_type == "tv" else None)
    )

    title_zh = _extract_tmdb_title(details_zh, normalized_media_type)
    title_collection = title
    title_en = _extract_tmdb_title(details_en, normalized_media_type)
    resolved_title = title_zh or title_collection or title_en or "Unknown Title"

    resolved_title = renamer.sanitize_for_emby(resolved_title, ascii_only=False)
    if not resolved_title:
        resolved_title = "Unknown Title"

    return TmdbNamingInfo(
        tmdb_id=resolved_tmdb_id,
        media_type=normalized_media_type,
        category=category,
        title=resolved_title,
        year=resolved_year,
        season_count=season_count,
    )


def _entry_name(entry: Dict[str, Any]) -> str:
    return entry.get("file_name") or entry.get("name") or ""


def _entry_is_dir(entry: Dict[str, Any]) -> bool:
    if isinstance(entry.get("dir"), bool):
        return entry["dir"]
    if isinstance(entry.get("dir"), int):
        return entry["dir"] == 1
    file_type = entry.get("file_type")
    if isinstance(file_type, int):
        return file_type in (0, 2)
    return False


async def wait_for_transfer_task(
    client: QuarkTransferClient,
    task_id: str,
    *,
    max_retries: int = 60,
    interval_seconds: float = 1.0,
) -> bool:
    if not task_id:
        return True

    for retry_index in range(max_retries):
        status = await client.get_task_status(task_id, retry_index)
        if status and status.status == 2:
            return True
        await asyncio.sleep(interval_seconds)
    return False


async def transfer_share_to_target_fid(
    client: QuarkTransferClient,
    share_url: str,
    target_fid: str,
    *,
    flatten_single_root: bool = True,
) -> Tuple[bool, str, List[Dict[str, Any]], str]:
    is_valid, pwd_id, stoken = await client.validate_share_link(share_url)
    if not is_valid or not pwd_id or not stoken:
        return False, "分享链接无效或已失效", [], ""

    detail_resp = await client.get_detail(pwd_id, stoken, "0")
    if detail_resp.get("code") != 0:
        msg = detail_resp.get("message") or "获取分享文件失败"
        return False, f"获取分享文件失败: {msg}", [], ""

    source_items = detail_resp.get("data", {}).get("list", []) or []

    if flatten_single_root:
        max_depth = 5
        depth = 0
        flatten_path: List[str] = []

        while depth < max_depth and len(source_items) == 1 and _entry_is_dir(source_items[0]):
            parent = source_items[0]
            parent_fid = parent.get("fid")
            parent_name = _entry_name(parent) or str(parent_fid or "")
            if not parent_fid:
                logger.warning("flatten_single_root: 目录缺少 fid，停止穿透: %s", parent_name)
                break

            sub_resp = await client.get_detail(pwd_id, stoken, parent_fid)
            if sub_resp.get("code") != 0:
                msg = sub_resp.get("message") or "获取目录详情失败"
                logger.warning(
                    "flatten_single_root: 穿透失败，停止在第 %d 层: name=%s, fid=%s, message=%s",
                    depth + 1,
                    parent_name,
                    parent_fid,
                    msg,
                )
                break

            sub_items = sub_resp.get("data", {}).get("list", []) or []
            if not sub_items:
                logger.info(
                    "flatten_single_root: 目录为空，停止穿透: name=%s, fid=%s, depth=%d",
                    parent_name,
                    parent_fid,
                    depth + 1,
                )
                break

            flatten_path.append(parent_name)
            source_items = sub_items
            depth += 1

        if depth > 0:
            logger.info(
                "flatten_single_root: 已穿透 %d 层，路径=%s，最终待转存项=%d",
                depth,
                " / ".join(flatten_path),
                len(source_items),
            )
            if depth >= max_depth and len(source_items) == 1 and _entry_is_dir(source_items[0]):
                current_name = _entry_name(source_items[0]) or str(source_items[0].get("fid") or "")
                logger.info(
                    "flatten_single_root: 达到最大穿透层数 %d，保留当前目录继续转存: %s",
                    max_depth,
                    current_name,
                )

    if not source_items:
        return False, "分享链接中没有可转存的文件", [], ""

    fid_list = [item.get("fid", "") for item in source_items]
    fid_token_list = [item.get("share_fid_token", "") for item in source_items]
    if not all(fid_list):
        return False, "分享文件列表缺少 fid，无法转存", [], ""

    save_resp = await client.save_file(fid_list, fid_token_list, target_fid, pwd_id, stoken)
    if save_resp.get("status") != 200 or save_resp.get("code") != 0:
        msg = save_resp.get("message") or "转存失败"
        return False, f"转存失败: {msg}", [], ""

    task_id = save_resp.get("data", {}).get("task_id") or ""
    return True, "转存提交成功", source_items, task_id


async def _get_or_create_subdir_fid(
    client: QuarkTransferClient,
    parent_fid: str,
    dir_name: str,
) -> Optional[str]:
    ls_resp = await client.ls_dir(parent_fid)
    if ls_resp.get("code") == 0:
        for item in ls_resp.get("data", {}).get("list", []) or []:
            if _entry_is_dir(item) and _entry_name(item) == dir_name:
                return item.get("fid")

    created = await client.create_dir(dir_name, pdir_fid=parent_fid)
    if created:
        return created

    ls_resp = await client.ls_dir(parent_fid)
    if ls_resp.get("code") == 0:
        for item in ls_resp.get("data", {}).get("list", []) or []:
            if _entry_is_dir(item) and _entry_name(item) == dir_name:
                return item.get("fid")
    return None


async def _dir_contains_fid(client: QuarkTransferClient, dir_fid: str, fid: str) -> bool:
    """检查目录下是否存在指定 fid。"""
    resp = await client.ls_dir(dir_fid)
    if resp.get("code") != 0:
        return False
    target = str(fid)
    for item in resp.get("data", {}).get("list", []) or []:
        if str(item.get("fid", "")) == target:
            return True
    return False


async def collect_video_files(
    client: QuarkTransferClient,
    root_fid: str,
    renamer: Renamer,
) -> List[Dict[str, Any]]:
    """
    Recursively collect all video files under a root directory.
    """
    collected: List[Dict[str, Any]] = []
    stack: List[Tuple[str, str]] = [(root_fid, "")]
    visited: Set[str] = set()

    while stack:
        current_fid, current_dir_name = stack.pop()
        if current_fid in visited:
            continue
        visited.add(current_fid)

        resp = await client.ls_dir(current_fid)
        if resp.get("code") != 0:
            logger.warning("Skip listing directory due to API error: fid=%s", current_fid)
            continue

        for item in resp.get("data", {}).get("list", []) or []:
            child_fid = item.get("fid")
            child_name = _entry_name(item)
            if not child_fid or not child_name:
                continue

            if _entry_is_dir(item):
                stack.append((child_fid, child_name))
                continue

            if not renamer.is_video_file(child_name):
                continue

            season, episode = renamer.extract_episode_info(child_name)
            parent_season, _ = renamer.extract_episode_info(current_dir_name)
            if season is None and parent_season is not None:
                season = parent_season
            if season is None and episode is not None:
                season = 1

            is_special = renamer.is_special_content(child_name, current_dir_name)
            is_extra = renamer.is_extra_content(child_name, current_dir_name)
            if is_special:
                season = 0

            collected.append(
                {
                    "fid": child_fid,
                    "file_name": child_name,
                    "size": item.get("size", 0),
                    "season": season,
                    "episode": episode,
                    "is_special": is_special,
                    "is_extra": is_extra,
                    "parent_fid": current_fid,
                    "parent_name": current_dir_name,
                }
            )

    if collected:
        dir_seasons = set()
        root_items = []
        for item in collected:
            if item["parent_fid"] != root_fid:
                if item["season"] is not None and not item["is_special"]:
                    dir_seasons.add(item["season"])
            else:
                root_items.append(item)
        
        if root_items and dir_seasons:
            inferred_season = max(dir_seasons) + 1
            for item in root_items:
                if (item["season"] is None or item["season"] == 1) and not item["is_special"]:
                    item["season"] = inferred_season
                    logger.info(
                        "推断散落文件季号(可能为续作): %s -> Season %d",
                        item["file_name"], inferred_season
                    )

    return collected


def _build_video_action(
    *,
    item: Dict[str, Any],
    title: str,
    year: Optional[int],
    media_type: str,
    renamer: Renamer,
    season: Optional[int] = None,
    episode: Optional[int] = None,
) -> Dict[str, Any]:
    old_name = str(item.get("file_name") or "")
    ext = renamer.get_file_extension(old_name)

    if media_type == "movie":
        new_name = renamer.build_movie_filename(title, year, ext)
    else:
        safe_season = int(season or 1)
        safe_episode = int(episode or 1)
        new_name = renamer.build_episode_filename(title, year, safe_season, safe_episode, ext)

    stem, _ = os.path.splitext(old_name)
    suffix = renamer.sanitize_for_emby(stem, ascii_only=False)
    suffix = suffix[:80] if suffix else ""
    fallback_name = None
    if suffix:
        base, ext2 = os.path.splitext(new_name)
        fallback_name = f"{base} - {suffix}{ext2}"

    return {
        "fid": item.get("fid"),
        "old_name": old_name,
        "new_name": new_name,
        "fallback_name": fallback_name,
        "parent_fid": item.get("parent_fid"),
        "season": season,
        "episode": episode,
        "quality_score": _quality_score(old_name, item.get("size")),
    }


async def reorganize_to_emby_structure(
    client: QuarkTransferClient,
    root_fid: str,
    root_path: str,
    video_files: List[Dict[str, Any]],
    renamer: Renamer,
    title: str,
    year: Optional[int],
    media_type: str,
    *,
    keep_extras: bool = False,
    dry_run: bool = False,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Reorganize videos into Emby-compatible structure.
    """
    normalized_media_type = "movie" if media_type == "movie" else "tv"
    actions: List[Dict[str, Any]] = []
    dropped_fids: Set[str] = set()
    retained_fids: Set[str] = set()

    if normalized_media_type == "movie":
        candidates = []
        for item in video_files:
            fid = item.get("fid")
            if not fid:
                continue
            if item.get("is_extra") and not keep_extras:
                dropped_fids.add(fid)
                continue
            candidates.append(item)

        if candidates:
            best = max(
                candidates,
                key=lambda x: _quality_score(str(x.get("file_name") or ""), x.get("size")),
            )
            for item in candidates:
                fid = item.get("fid")
                if not fid:
                    continue
                if item is best:
                    action = _build_video_action(
                        item=item,
                        title=title,
                        year=year,
                        media_type="movie",
                        renamer=renamer,
                    )
                    actions.append(action)
                    retained_fids.add(fid)
                else:
                    dropped_fids.add(fid)
    else:
        grouped: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        special_counter = 1

        for item in video_files:
            fid = item.get("fid")
            if not fid:
                continue
            if item.get("is_extra") and not keep_extras:
                dropped_fids.add(fid)
                continue

            season = item.get("season")
            episode = item.get("episode")
            is_special = bool(item.get("is_special"))

            if is_special:
                season = 0
            if season is None:
                season = 1

            if episode is None:
                if int(season) == 0:
                    episode = special_counter
                    special_counter += 1
                else:
                    dropped_fids.add(fid)
                    continue

            action = _build_video_action(
                item=item,
                title=title,
                year=year,
                media_type="tv",
                renamer=renamer,
                season=int(season),
                episode=int(episode),
            )
            grouped.setdefault((int(season), int(episode)), []).append(action)

        for (s_num, e_num), candidates in grouped.items():
            best = max(candidates, key=lambda x: x.get("quality_score") or (0, 0, 0, 0, 0))
            if len(candidates) > 1:
                logger.info(
                    "S%02dE%02d 存在 %d 个候选文件，已保留质量最高的: %s (%s 字节)",
                    s_num, e_num, len(candidates),
                    best.get("old_name"),
                    best.get("size")
                )
            actions.append(best)
            kept_fid = best.get("fid")
            if kept_fid:
                retained_fids.add(kept_fid)
            for candidate in candidates:
                if candidate is best:
                    continue
                candidate_fid = candidate.get("fid")
                if candidate_fid:
                    dropped_fids.add(candidate_fid)

    total = len(actions)
    current = 0
    success_count = 0
    skipped_count = 0
    failed_count = 0

    yield build_event_payload(
        event_type="log",
        current=0,
        total=total,
        message=f"{'[DRY-RUN] ' if dry_run else ''}开始重组目录: {root_path}",
        level="info",
    )

    if total == 0:
        yield build_event_payload(
            event_type="complete",
            current=0,
            total=0,
            message="未发现可重组的视频文件",
            level="warning",
            success=0,
            skipped=0,
            failed=0,
            dry_run=dry_run,
            retained_fids=sorted(retained_fids),
            dropped_fids=sorted(dropped_fids),
        )
        return

    season_dir_fids: Dict[int, str] = {}
    for action in actions:
        current += 1
        fid = action.get("fid")
        old_name = action.get("old_name", "")
        new_name = action.get("new_name", "")
        source_parent_fid = action.get("parent_fid")
        target_fid = root_fid

        if not fid:
            failed_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"缺少文件 fid，跳过: {old_name}",
                level="error",
            )
            continue

        if normalized_media_type == "tv":
            season = int(action.get("season") or 1)
            if season not in season_dir_fids:
                season_dir_name = renamer.build_season_folder_name(season)
                season_dir_fid = f"dry-run-season-{season:02d}" if dry_run else await _get_or_create_subdir_fid(client, root_fid, season_dir_name)
                if not season_dir_fid:
                    failed_count += 1
                    yield build_event_payload(
                        event_type="log",
                        current=current,
                        total=total,
                        message=f"创建季目录失败: {season_dir_name}",
                        level="error",
                    )
                    yield build_event_payload(
                        event_type="progress",
                        current=current,
                        total=total,
                        message=f"进度: {current}/{total}",
                        level="info",
                    )
                    continue
                season_dir_fids[season] = season_dir_fid
            target_fid = season_dir_fids[season]

        move_ok = True
        if source_parent_fid and source_parent_fid != target_fid:
            move_ok = True
            move_attempts = 0
            if not dry_run:
                move_ok = False
                while move_attempts < 2 and not move_ok:
                    move_attempts += 1
                    move_ok = await client.move_file([fid], target_fid, current_dir_fid=source_parent_fid)
                    if move_ok:
                        break

                    # 某些场景接口返回失败但实际已移动，按 fid 二次确认。
                    in_target = await _dir_contains_fid(client, target_fid, str(fid))
                    if in_target:
                        logger.warning(
                            "移动接口返回失败但文件已在目标目录: fid=%s, target_fid=%s, attempt=%s",
                            fid,
                            target_fid,
                            move_attempts,
                        )
                        move_ok = True
                        break

                    if move_attempts < 2:
                        await asyncio.sleep(0.35)

            if not move_ok:
                failed_count += 1
                logger.error(
                    "移动文件失败: fid=%s, source_parent_fid=%s, target_fid=%s, file=%s, attempts=%s",
                    fid,
                    source_parent_fid,
                    target_fid,
                    old_name,
                    move_attempts,
                )
                yield build_event_payload(
                    event_type="log",
                    current=current,
                    total=total,
                    message=f"移动失败: {old_name}",
                    level="error",
                    fid=fid,
                    source_parent_fid=source_parent_fid,
                    target_fid=target_fid,
                    move_attempts=move_attempts,
                )
                yield build_event_payload(
                    event_type="progress",
                    current=current,
                    total=total,
                    message=f"进度: {current}/{total}",
                    level="info",
                )
                continue
            if dry_run:
                yield build_event_payload(
                    event_type="log",
                    current=current,
                    total=total,
                    message=f"[DRY-RUN] 计划移动: {old_name}",
                    level="info",
                )
            else:
                await asyncio.sleep(0.2)

        if not new_name or new_name == old_name:
            skipped_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"名称已规范，跳过重命名: {old_name}",
                level="info",
            )
            yield build_event_payload(
                event_type="progress",
                current=current,
                total=total,
                message=f"进度: {current}/{total}",
                level="info",
            )
            continue

        rename_ok = True if dry_run else await client.rename(fid, new_name)
        final_name = new_name
        if not rename_ok and not dry_run:
            fallback_name = action.get("fallback_name")
            if fallback_name and fallback_name != old_name:
                rename_ok = await client.rename(fid, fallback_name)
                if rename_ok:
                    final_name = fallback_name

        if rename_ok:
            success_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"{'[DRY-RUN] 计划重命名' if dry_run else '重命名'}: {old_name} -> {final_name}",
                level="info",
            )
        else:
            failed_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"重命名失败: {old_name} -> {new_name}",
                level="error",
            )

        if not dry_run:
            await asyncio.sleep(0.2)
        yield build_event_payload(
            event_type="progress",
            current=current,
            total=total,
            message=f"进度: {current}/{total}",
            level="info",
        )

    yield build_event_payload(
        event_type="complete",
        current=total,
        total=total,
        message=f"目录重组完成: 成功 {success_count}, 跳过 {skipped_count}, 失败 {failed_count}",
        level="info",
        success=success_count,
        skipped=skipped_count,
        failed=failed_count,
        dry_run=dry_run,
        retained_fids=sorted(retained_fids),
        dropped_fids=sorted(dropped_fids),
    )


async def cleanup_non_video_files(
    client: QuarkTransferClient,
    root_fid: str,
    renamer: Renamer,
    *,
    protected_video_fids: Optional[Set[str]] = None,
    keep_subtitles: bool = False,
    dry_run: bool = False,
    delete_non_video: bool = True,
    delete_unselected_videos: bool = True,
    delete_empty_dirs: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Delete non-video files, unselected videos and empty directories.
    """
    protected = set(protected_video_fids or set())
    files_to_delete: List[Tuple[str, str, str]] = []
    dir_candidates: List[Tuple[str, str, int]] = []
    stack: List[Tuple[str, int]] = [(root_fid, 0)]
    visited: Set[str] = set()

    while stack:
        current_fid, depth = stack.pop()
        if current_fid in visited:
            continue
        visited.add(current_fid)

        resp = await client.ls_dir(current_fid)
        if resp.get("code") != 0:
            continue

        for item in resp.get("data", {}).get("list", []) or []:
            child_fid = item.get("fid")
            child_name = _entry_name(item)
            if not child_fid or not child_name:
                continue

            if _entry_is_dir(item):
                if delete_empty_dirs:
                    dir_candidates.append((child_fid, child_name, depth + 1))
                stack.append((child_fid, depth + 1))
                continue

            if renamer.is_video_file(child_name):
                if delete_unselected_videos and child_fid not in protected:
                    files_to_delete.append((child_fid, child_name, "unselected_video"))
            else:
                if not delete_non_video:
                    continue
                if keep_subtitles and renamer.is_subtitle_file(child_name):
                    continue
                files_to_delete.append((child_fid, child_name, "non_video"))

    total = len(files_to_delete) + len(dir_candidates)
    current = 0
    deleted_count = 0
    planned_count = 0
    skipped_count = 0
    failed_count = 0

    yield build_event_payload(
        event_type="log",
        current=0,
        total=total,
        message=f"{'[DRY-RUN] ' if dry_run else ''}开始清理阶段",
        level="info",
    )

    for fid, name, reason in files_to_delete:
        current += 1
        ok = True if dry_run else await client.delete_file([fid])
        if ok:
            hint = "非视频" if reason == "non_video" else "未选中视频"
            if dry_run:
                planned_count += 1
            else:
                deleted_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"{'[DRY-RUN] 计划删除' if dry_run else '删除'}{hint}: {name}",
                level="info",
            )
        else:
            failed_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"删除失败: {name}",
                level="error",
            )
        if not dry_run:
            await asyncio.sleep(0.2)
        yield build_event_payload(
            event_type="progress",
            current=current,
            total=total,
            message=f"进度: {current}/{total}",
            level="info",
        )

    for fid, name, _depth in sorted(dir_candidates, key=lambda x: x[2], reverse=True):
        current += 1
        if re.match(r"^Season\s+\d+$", name, re.IGNORECASE):
            skipped_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"跳过季目录: {name}",
                level="info",
            )
            yield build_event_payload(
                event_type="progress",
                current=current,
                total=total,
                message=f"进度: {current}/{total}",
                level="info",
            )
            continue

        ls_resp = await client.ls_dir(fid)
        children = ls_resp.get("data", {}).get("list", []) if ls_resp.get("code") == 0 else None
        if children is None or len(children) > 0:
            skipped_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"目录非空，跳过: {name}",
                level="info",
            )
            yield build_event_payload(
                event_type="progress",
                current=current,
                total=total,
                message=f"进度: {current}/{total}",
                level="info",
            )
            continue

        ok = True if dry_run else await client.delete_file([fid])
        if ok:
            if dry_run:
                planned_count += 1
            else:
                deleted_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"{'[DRY-RUN] 计划删除空目录' if dry_run else '删除空目录'}: {name}",
                level="info",
            )
        else:
            failed_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"删除空目录失败: {name}",
                level="error",
            )
        if not dry_run:
            await asyncio.sleep(0.2)
        yield build_event_payload(
            event_type="progress",
            current=current,
            total=total,
            message=f"进度: {current}/{total}",
            level="info",
        )

    yield build_event_payload(
        event_type="complete",
        current=total,
        total=total,
        message=f"清理完成: 删除 {deleted_count}, 计划删除 {planned_count}, 跳过 {skipped_count}, 失败 {failed_count}",
        level="info",
        deleted=deleted_count,
        planned=planned_count,
        skipped=skipped_count,
        failed=failed_count,
        dry_run=dry_run,
    )


def _quality_score(name: str, size: Optional[int]) -> Tuple[int, int, int, int, int]:
    """
    评估剧集文件质量，分数越高质量越好。
    评分维度：分辨率 > HDR/DV > 片源 > 编码 > 文件大小。
    """
    text = (name or "").lower()

    resolution_score = 0
    if _RES_4K.search(text):
        resolution_score = 4
    elif _RES_1080P.search(text):
        resolution_score = 3
    elif _RES_720P.search(text):
        resolution_score = 2
    elif _RES_LOW.search(text):
        resolution_score = 1

    hdr_score = 0
    if _HDR_DV.search(text):
        hdr_score = 3
    elif _HDR10_PLUS.search(text):
        hdr_score = 2
    elif _HDR10.search(text):
        hdr_score = 1
    if _HDR_10BIT.search(text):
        hdr_score = max(hdr_score, 1)

    source_score = 0
    if _SRC_BLURAY.search(text):
        source_score = 4
    elif _SRC_WEB.search(text):
        source_score = 3
    elif "hdtv" in text:
        source_score = 2
    elif _SRC_DVD.search(text):
        source_score = 1

    codec_score = 0
    if _CODEC_H265.search(text):
        codec_score = 2
    elif _CODEC_H264.search(text):
        codec_score = 1

    return (resolution_score, hdr_score, source_score, codec_score, int(size or 0))

