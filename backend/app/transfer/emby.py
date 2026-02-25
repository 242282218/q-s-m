"""
Emby v1.6 命名与夸克云转存重命名工作流。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.quark.core.transfer_client import QuarkTransferClient
from app.services.tmdb import TmdbClient
from app.transfer.renamer import Renamer
from app.utils.events import build_event_payload

logger = logging.getLogger(__name__)


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
        if title and not title_matches:
            if normalized_media_type == "movie":
                search_results = await tmdb_client.search_movies(title, year)
            else:
                search_results = await tmdb_client.search_tv(title, year)
            best = _pick_best_search_result(search_results, year)
            best_id = best.get("id") if best else None
            if best_id and best_id != resolved_tmdb_id:
                resolved_tmdb_id = best_id
                details_zh = await tmdb_client.details(normalized_media_type, resolved_tmdb_id, language_override="zh-CN")
                details_en = await tmdb_client.details(normalized_media_type, resolved_tmdb_id, language_override="en-US")

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
    title_romanized = None
    if category == "anime" and resolved_tmdb_id and normalized_media_type == "tv":
        alt_titles = await tmdb_client.alternative_titles("tv", resolved_tmdb_id)
        title_romanized = pick_romanized_title(alt_titles, renamer)

    resolved_title = title_zh or title_collection or title_romanized or title_en or "Unknown Title"

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

    if flatten_single_root and len(source_items) == 1 and source_items[0].get("dir"):
        parent_fid = source_items[0].get("fid")
        if parent_fid:
            sub_resp = await client.get_detail(pwd_id, stoken, parent_fid)
            if sub_resp.get("code") == 0:
                sub_items = sub_resp.get("data", {}).get("list", []) or []
                if sub_items:
                    source_items = sub_items

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


async def ensure_season_directories(
    client: QuarkTransferClient,
    root_path: str,
    season_count: Optional[int],
    renamer: Renamer,
) -> None:
    if not season_count or season_count <= 0:
        return
    for season in range(1, season_count + 1):
        season_dir = renamer.build_season_folder_name(season)
        await client.mkdir(f"{root_path}/{season_dir}")


def _quality_score(name: str, size: Optional[int]) -> Tuple[int, int, int, int, int]:
    """
    评估剧集文件质量，分数越高质量越好。
    评分维度：分辨率 > HDR/DV > 片源 > 编码 > 文件大小。
    """
    text = (name or "").lower()

    resolution_score = 0
    if re.search(r"(2160p|4k|uhd)", text):
        resolution_score = 4
    elif "1080p" in text:
        resolution_score = 3
    elif "720p" in text:
        resolution_score = 2
    elif re.search(r"(576p|540p|480p)", text):
        resolution_score = 1

    hdr_score = 0
    if re.search(r"(dolby[\s\-]?vision|dv|dovi)", text):
        hdr_score = 3
    elif re.search(r"(hdr10\+|hdr10plus)", text):
        hdr_score = 2
    elif re.search(r"(hdr|hdr10)", text):
        hdr_score = 1
    if re.search(r"(10bit|10[\s\-]?bit)", text):
        hdr_score = max(hdr_score, 1)

    source_score = 0
    if re.search(r"(blu[\s\-]?ray|bdrip|bdremux|remux)", text):
        source_score = 4
    elif re.search(r"(web[\s\-]?(dl|rip)|webrip)", text):
        source_score = 3
    elif "hdtv" in text:
        source_score = 2
    elif re.search(r"(dvdrip|dvd)", text):
        source_score = 1

    codec_score = 0
    if re.search(r"(x265|h\.?265|hevc|av1)", text):
        codec_score = 2
    elif re.search(r"(x264|h\.?264|avc)", text):
        codec_score = 1

    return (resolution_score, hdr_score, source_score, codec_score, int(size or 0))


def _build_rename_plan(
    item: Dict[str, Any],
    *,
    normalized_media_type: str,
    season_hint: Optional[int],
    renamer: Renamer,
    title: str,
    year: Optional[int],
) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    fid = item.get("fid")
    old_name = _entry_name(item)
    if not fid or not old_name:
        return None, season_hint

    if _entry_is_dir(item):
        dir_season, _ = renamer.extract_episode_info(old_name)
        next_hint = dir_season or season_hint
        if normalized_media_type == "tv" and dir_season is not None:
            new_dir_name = renamer.build_season_folder_name(dir_season)
            if new_dir_name != old_name:
                return (
                    {
                        "kind": "dir",
                        "fid": fid,
                        "old_name": old_name,
                        "new_name": new_dir_name,
                    },
                    next_hint,
                )
        return None, next_hint

    if not renamer.is_video_file(old_name):
        return (
            {
                "kind": "skip",
                "old_name": old_name,
                "reason": "non_video",
            },
            season_hint,
        )

    ext = renamer.get_file_extension(old_name)
    if normalized_media_type == "movie":
        new_name = renamer.build_movie_filename(title, year, ext)
    else:
        extracted_season, episode = renamer.extract_episode_info(old_name)
        season = extracted_season or season_hint or 1
        extra_like = re.search(r"(NCOP|NCED|OP|ED|OVA|SPECIAL|SP)", old_name, re.IGNORECASE) is not None
        if episode is None and extra_like:
            episode = 0
        if episode is None:
            return (
                {
                    "kind": "skip",
                    "old_name": old_name,
                    "reason": "episode_not_found",
                },
                season_hint,
            )
        new_name = renamer.build_episode_filename(title, year, season, episode, ext)
        if episode == 0:
            stem, _ = os.path.splitext(old_name)
            extra_suffix = renamer.sanitize_for_emby(stem, ascii_only=True)
            extra_suffix = extra_suffix[:80] if extra_suffix else ""
            if extra_suffix:
                base, ext2 = os.path.splitext(new_name)
                new_name = f"{base} - {extra_suffix}{ext2}"

    if new_name == old_name:
        return (
            {
                "kind": "skip",
                "old_name": old_name,
                "reason": "already_standard",
            },
            season_hint,
        )

    stem, _ = os.path.splitext(old_name)
    suffix = renamer.sanitize_for_emby(stem, ascii_only=True)
    suffix = suffix[:80] if suffix else ""
    fallback_name = None
    if suffix:
        base, ext2 = os.path.splitext(new_name)
        fallback_name = f"{base} - {suffix}{ext2}"

    return (
        {
            "kind": "file",
            "fid": fid,
            "old_name": old_name,
            "new_name": new_name,
            "fallback_name": fallback_name,
            "season": season if normalized_media_type != "movie" else None,
            "episode": episode if normalized_media_type != "movie" else None,
            "quality_score": _quality_score(old_name, item.get("size")),
        },
        season_hint,
    )


class RenameSavedTreeRunner:
    def __init__(
        self,
        *,
        client: QuarkTransferClient,
        root_fid: str,
        renamer: Renamer,
        title: str,
        year: Optional[int],
        media_type: str,
    ) -> None:
        self._client = client
        self._root_fid = root_fid
        self._renamer = renamer
        self._title = title
        self._year = year
        self._media_type = media_type

    def __aiter__(self) -> AsyncGenerator[Dict[str, Any], None]:
        return _rename_saved_tree_to_emby_events(
            client=self._client,
            root_fid=self._root_fid,
            renamer=self._renamer,
            title=self._title,
            year=self._year,
            media_type=self._media_type,
        )

    def __await__(self):
        async def _consume() -> int:
            renamed_count = 0
            async for event in _rename_saved_tree_to_emby_events(
                client=self._client,
                root_fid=self._root_fid,
                renamer=self._renamer,
                title=self._title,
                year=self._year,
                media_type=self._media_type,
            ):
                if event.get("type") == "complete":
                    renamed_count = int(event.get("success", 0))
            return renamed_count

        return _consume().__await__()


async def _rename_saved_tree_to_emby_events(
    client: QuarkTransferClient,
    root_fid: str,
    renamer: Renamer,
    title: str,
    year: Optional[int],
    media_type: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    normalized_media_type = "movie" if media_type == "movie" else "tv"
    plan: List[Dict[str, Any]] = []
    stack: List[Tuple[str, Optional[int]]] = [(root_fid, None)]
    visited = set()

    while stack:
        current_fid, season_hint = stack.pop()
        if current_fid in visited:
            continue
        visited.add(current_fid)

        resp = await client.ls_dir(current_fid)
        if resp.get("code") != 0:
            logger.warning(f"列目录失败，跳过: fid={current_fid}")
            continue

        items = resp.get("data", {}).get("list", []) or []
        for item in items:
            action, next_hint = _build_rename_plan(
                item,
                normalized_media_type=normalized_media_type,
                season_hint=season_hint,
                renamer=renamer,
                title=title,
                year=year,
            )
            if action:
                plan.append(action)

            if _entry_is_dir(item):
                child_fid = item.get("fid")
                if child_fid:
                    stack.append((child_fid, next_hint))

    if normalized_media_type == "tv":
        grouped: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for action in plan:
            if action.get("kind") != "file":
                continue
            season = action.get("season")
            episode = action.get("episode")
            if season is None or episode is None:
                continue
            grouped.setdefault((int(season), int(episode)), []).append(action)

        for key, candidates in grouped.items():
            if len(candidates) <= 1:
                continue
            best = max(candidates, key=lambda x: x.get("quality_score") or (0, 0, 0, 0, 0))
            for candidate in candidates:
                if candidate is best:
                    continue
                candidate["kind"] = "skip"
                candidate["reason"] = "lower_quality_duplicate"
                candidate["kept_name"] = best.get("old_name", "")

    total = len(plan)
    current = 0
    success_count = 0
    skipped_count = 0
    failed_count = 0

    yield build_event_payload(
        event_type="log",
        current=0,
        total=total,
        message=f"开始重命名: {title} (共 {total} 项)",
        level="info",
    )

    if total == 0:
        yield build_event_payload(
            event_type="complete",
            current=0,
            total=0,
            message="无可处理文件",
            level="info",
            success=0,
            skipped=0,
            failed=0,
        )
        return

    for action in plan:
        current += 1
        kind = action.get("kind")

        if kind == "skip":
            skipped_count += 1
            reason = action.get("reason")
            old_name = action.get("old_name", "")
            if reason == "non_video":
                message = f"跳过非视频文件: {old_name}"
            elif reason == "episode_not_found":
                message = f"无法识别集数，跳过: {old_name}"
            elif reason == "lower_quality_duplicate":
                kept_name = action.get("kept_name", "")
                message = f"同集多版本，跳过较低质量: {old_name} (保留: {kept_name})"
            else:
                message = f"名称已标准化，跳过: {old_name}"
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=message,
                level="warning",
            )
            yield build_event_payload(
                event_type="progress",
                current=current,
                total=total,
                message=f"进度: {current}/{total}",
                level="info",
            )
            continue

        fid = action.get("fid")
        old_name = action.get("old_name", "")
        new_name = action.get("new_name", "")
        if not fid or not new_name:
            failed_count += 1
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"重命名失败: {old_name} -> {new_name}",
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

        renamed_name = new_name
        success = await client.rename(fid, new_name)
        if not success and kind == "file":
            fallback_name = action.get("fallback_name")
            if fallback_name and fallback_name != old_name:
                success = await client.rename(fid, fallback_name)
                if success:
                    renamed_name = fallback_name

        if success:
            success_count += 1
            prefix = "目录" if kind == "dir" else "文件"
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"{prefix}: {old_name} -> {renamed_name} ✓",
                level="info",
            )
        else:
            failed_count += 1
            prefix = "目录" if kind == "dir" else "文件"
            logger.warning(f"{prefix}重命名失败: {old_name} -> {new_name}")
            yield build_event_payload(
                event_type="log",
                current=current,
                total=total,
                message=f"{prefix}: {old_name} -> {new_name} ✗",
                level="error",
            )

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
        message=f"重命名完成: 成功 {success_count}, 跳过 {skipped_count}, 失败 {failed_count}",
        level="info",
        success=success_count,
        skipped=skipped_count,
        failed=failed_count,
    )


def rename_saved_tree_to_emby(
    client: QuarkTransferClient,
    root_fid: str,
    renamer: Renamer,
    title: str,
    year: Optional[int],
    media_type: str,
) -> RenameSavedTreeRunner:
    return RenameSavedTreeRunner(
        client=client,
        root_fid=root_fid,
        renamer=renamer,
        title=title,
        year=year,
        media_type=media_type,
    )
