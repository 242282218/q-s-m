"""
文件重命名引擎
根据 TMDB 信息将文件重命名为 Emby/Kodi 兼容格式
"""
import re
import os
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class RenameResult:
    """重命名结果"""
    original_name: str
    new_name: str
    new_path: str
    season: Optional[int] = None
    episode: Optional[int] = None


class Renamer:
    """
    文件重命名引擎
    
    支持的媒体类型:
    - movie: 电影
    - tv: 电视剧
    - anime: 动漫
    - documentary: 纪录片
    """
    
    # 视频文件扩展名
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.rmvb'}
    
    # 集数匹配正则表达式 (按优先级排序)
    EPISODE_PATTERNS = [
        # S01E01 格式
        r'[Ss](\d{1,2})[Ee](\d{1,3})',
        # 第01集 格式
        r'第(\d{1,3})[集话話]',
        # EP01 格式
        r'[Ee][Pp]?(\d{1,3})',
        # [01] 格式
        r'\[(\d{2,3})\]',
        # - 01 格式 (末尾)
        r'[-_]\s*(\d{2,3})(?:\s|$|\[)',
        # E01 格式
        r'[Ee](\d{1,3})(?:\s|$|\[)',
        # 01话/01集 格式
        r'(\d{1,3})[话話集]',
    ]
    
    # 季数匹配正则表达式
    SEASON_PATTERNS = [
        r'[Ss](\d{1,2})',
        r'[Ss]eason\s*(\d{1,2})',
        r'第(\d{1,2})[季部]',
    ]
    
    # 分类到目录的映射
    CATEGORY_DIRS = {
        'movie': '/收藏TV/Movies',
        'tv': '/收藏TV/TV Shows',
        'anime': '/收藏TV/Anime',
        'documentary': '/收藏TV/Documentary',
    }

    def __init__(self):
        pass

    def extract_episode_info(self, filename: str) -> Tuple[Optional[int], Optional[int]]:
        """
        从文件名中提取季数和集数
        
        Args:
            filename: 文件名
            
        Returns:
            (season, episode)
        """
        season = None
        episode = None
        
        # 提取季数
        for pattern in self.SEASON_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                season = int(match.group(1))
                break
        
        # 提取集数
        for pattern in self.EPISODE_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                # S01E01 格式会同时匹配季和集
                if 'Ss' in pattern or 'Ee' in pattern.lower()[:2]:
                    groups = match.groups()
                    if len(groups) == 2:
                        season = int(groups[0])
                        episode = int(groups[1])
                    else:
                        episode = int(groups[0])
                else:
                    episode = int(match.group(1))
                break
        
        # 默认季数为 1
        if episode is not None and season is None:
            season = 1
        
        return season, episode

    def get_file_extension(self, filename: str) -> str:
        """获取文件扩展名"""
        _, ext = os.path.splitext(filename)
        return ext.lower()

    def is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        ext = self.get_file_extension(filename)
        return ext in self.VIDEO_EXTENSIONS

    def sanitize_filename(self, name: str) -> str:
        """
        清理文件名，移除非法字符
        
        Args:
            name: 原始名称
            
        Returns:
            清理后的名称
        """
        # Windows 非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        name = re.sub(illegal_chars, '', name)
        # 多个空格替换为单个
        name = re.sub(r'\s+', ' ', name)
        # 去除首尾空格
        name = name.strip()
        return name

    def generate_movie_path(
        self,
        title: str,
        year: Optional[int],
        original_filename: str,
        category: str = 'movie'
    ) -> RenameResult:
        """
        生成电影的重命名路径
        
        格式: /收藏TV/Movies/{Title} ({Year})/{Title} ({Year}).ext
        
        Args:
            title: 电影标题
            year: 年份
            original_filename: 原始文件名
            category: 分类
            
        Returns:
            RenameResult
        """
        ext = self.get_file_extension(original_filename)
        title = self.sanitize_filename(title)
        
        if year:
            folder_name = f"{title} ({year})"
            new_name = f"{title} ({year}){ext}"
        else:
            folder_name = title
            new_name = f"{title}{ext}"
        
        base_dir = self.CATEGORY_DIRS.get(category, self.CATEGORY_DIRS['movie'])
        new_path = f"{base_dir}/{folder_name}/{new_name}"
        
        return RenameResult(
            original_name=original_filename,
            new_name=new_name,
            new_path=new_path,
        )

    def generate_tv_path(
        self,
        title: str,
        year: Optional[int],
        original_filename: str,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        category: str = 'tv'
    ) -> RenameResult:
        """
        生成电视剧的重命名路径
        
        格式: /收藏TV/TV Shows/{Title} ({Year})/Season {S}/{Title} - S{xx}E{xx}.ext
        
        Args:
            title: 剧名
            year: 年份
            original_filename: 原始文件名
            season: 季数 (如果为 None，会尝试从文件名提取)
            episode: 集数 (如果为 None，会尝试从文件名提取)
            category: 分类
            
        Returns:
            RenameResult
        """
        ext = self.get_file_extension(original_filename)
        title = self.sanitize_filename(title)
        
        # 尝试从文件名提取季数和集数
        if season is None or episode is None:
            extracted_season, extracted_episode = self.extract_episode_info(original_filename)
            if season is None:
                season = extracted_season or 1
            if episode is None:
                episode = extracted_episode
        
        if year:
            show_folder = f"{title} ({year})"
        else:
            show_folder = title
        
        season_folder = f"Season {season}"
        
        if episode is not None:
            new_name = f"{title} - S{season:02d}E{episode:02d}{ext}"
        else:
            # 无法提取集数，保留原文件名
            new_name = original_filename
        
        base_dir = self.CATEGORY_DIRS.get(category, self.CATEGORY_DIRS['tv'])
        new_path = f"{base_dir}/{show_folder}/{season_folder}/{new_name}"
        
        return RenameResult(
            original_name=original_filename,
            new_name=new_name,
            new_path=new_path,
            season=season,
            episode=episode,
        )

    def generate_path(
        self,
        original_filename: str,
        title: str,
        year: Optional[int] = None,
        media_type: str = 'movie',
        category: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> RenameResult:
        """
        根据媒体类型生成重命名路径
        
        Args:
            original_filename: 原始文件名
            title: 标题
            year: 年份
            media_type: 媒体类型 (movie/tv)
            category: 分类 (movie/tv/anime/documentary)
            season: 季数 (仅电视剧)
            episode: 集数 (仅电视剧)
            
        Returns:
            RenameResult
        """
        # 自动确定分类
        if category is None:
            category = media_type
        
        if media_type == 'movie':
            return self.generate_movie_path(title, year, original_filename, category)
        else:
            return self.generate_tv_path(title, year, original_filename, season, episode, category)

    def generate_batch_paths(
        self,
        files: List[str],
        title: str,
        year: Optional[int] = None,
        media_type: str = 'movie',
        category: Optional[str] = None,
    ) -> List[RenameResult]:
        """
        批量生成重命名路径
        
        Args:
            files: 文件名列表
            title: 标题
            year: 年份
            media_type: 媒体类型
            category: 分类
            
        Returns:
            RenameResult 列表
        """
        results = []
        
        for filename in files:
            # 只处理视频文件
            if not self.is_video_file(filename):
                continue
            
            result = self.generate_path(
                original_filename=filename,
                title=title,
                year=year,
                media_type=media_type,
                category=category,
            )
            results.append(result)
        
        # 对电视剧按集数排序
        if media_type == 'tv':
            results.sort(key=lambda x: (x.season or 0, x.episode or 0))
        
        return results
