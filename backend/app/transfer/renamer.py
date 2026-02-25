"""
文件重命名引擎
根据 TMDB 信息将文件重命名为 Emby/Kodi 兼容格式
"""
import re
import os
import unicodedata
from typing import Optional, Tuple, List, Dict
from dataclasses import dataclass

from app.core.config import get_settings


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
    
    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.rmvb'}
    SUBTITLE_EXTENSIONS = {'.srt', '.ass', '.ssa', '.sub', '.vtt'}
    
    _SPECIAL_KEYWORDS_RAW = [
        r"\bSP\d*\b",
        r"\bSpecials?\b",
        r"\bOVA\b",
        r"\bOAD\b",
        r"\bONA\b",
        r"\bRecap\b",
        r"特别篇",
        r"特別篇",
        r"番外",
    ]
    _EXTRAS_KEYWORDS_RAW = [
        r"\bextras?\b",
        r"behind\s*the\s*scenes?",
        r"making\s*of",
        r"deleted?\s*scenes?",
        r"interviews?",
        r"trailers?",
        r"\bPV\b",
        r"\bNCOP\b",
        r"\bNCED\b",
        r"\bOP\d*\b",
        r"\bED\d*\b",
        r"花絮",
        r"幕后",
        r"預告",
        r"预告",
    ]
    _NOISE_DIR_KEYWORDS_RAW = [
        r"\b1080p\b",
        r"\b2160p\b",
        r"\b4k\b",
        r"\b720p\b",
        r"\bBDMV\b",
        r"\bCERTIFICATE\b",
        r"\bBACKUP\b",
        r"\bSample\b",
        r"@eaDir",
    ]
    
    SPECIAL_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in _SPECIAL_KEYWORDS_RAW]
    EXTRAS_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in _EXTRAS_KEYWORDS_RAW]
    NOISE_DIR_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in _NOISE_DIR_KEYWORDS_RAW]
    
    _EPISODE_PATTERNS_RAW = [
        r'[Ss](\d{1,2})[Ee](\d{1,3})',
        r'第(\d{1,3})[集话話]',
        r'[Ee][Pp]?(\d{1,3})',
        r'\[(\d{2,3})\]',
        r'[-_]\s*(\d{2,3})(?:\s|$|\[)',
        r'[Ee](\d{1,3})(?:\s|$|\[)',
        r'(\d{1,3})[话話集]',
        r'(?:^|[-_\s\.])(\d{1,3})(?:[_\s\.]|@|v\d|$)',
    ]
    _SEASON_PATTERNS_RAW = [
        r'[Ss](\d{1,2})',
        r'[Ss]eason\s*(\d{1,2})',
        r'第(\d{1,2})[季部]',
        r'第([一二三四五六七八九十]{1,3})[季部]',
    ]
    
    EPISODE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _EPISODE_PATTERNS_RAW]
    SEASON_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SEASON_PATTERNS_RAW]

    GARBLED_REPLACEMENTS = {
        "鏀惰棌TV": "影视收藏",
        "收藏TV": "影视收藏",
        "Movies": "电影",
        "TV Shows": "电视剧",
        "Anime": "动漫",
        "Documentary": "纪录片",
    }

    CHINESE_NUMERAL_MAP = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }

    def __init__(self):
        pass

    def _get_category_dirs(self) -> Dict[str, str]:
        settings = get_settings()
        return {
            'movie': settings.base_movie_dir,
            'tv': settings.base_tv_dir,
            'anime': settings.base_anime_dir,
            'documentary': settings.base_documentary_dir,
        }

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
        
        for pattern in self.SEASON_PATTERNS:
            match = pattern.search(filename)
            if match:
                parsed = self._parse_numeric_token(match.group(1))
                if parsed is not None:
                    season = parsed
                    break
        
        for idx, pattern in enumerate(self.EPISODE_PATTERNS):
            match = pattern.search(filename)
            if match:
                if idx == 0:
                    groups = match.groups()
                    if len(groups) == 2:
                        parsed_season = self._parse_numeric_token(groups[0])
                        parsed_episode = self._parse_numeric_token(groups[1])
                        if parsed_season is not None:
                            season = parsed_season
                        if parsed_episode is not None:
                            episode = parsed_episode
                    else:
                        parsed_episode = self._parse_numeric_token(groups[0])
                        if parsed_episode is not None:
                            episode = parsed_episode
                else:
                    parsed_episode = self._parse_numeric_token(match.group(1))
                    if parsed_episode is not None:
                        episode = parsed_episode
                if episode is not None:
                    if episode > 300:
                        episode = None
                    else:
                        break
        
        return season, episode

    def _parse_numeric_token(self, token: str) -> Optional[int]:
        """解析阿拉伯数字或中文数字（如 第一季 / 第十二季）。"""
        if not token:
            return None
        token = token.strip()
        if token.isdigit():
            return int(token)

        if all(ch in self.CHINESE_NUMERAL_MAP or ch == "十" for ch in token):
            if token == "十":
                return 10
            if "十" not in token:
                return self.CHINESE_NUMERAL_MAP.get(token)

            left, right = token.split("十", 1)
            tens = 1 if left == "" else self.CHINESE_NUMERAL_MAP.get(left, 0)
            ones = 0 if right == "" else self.CHINESE_NUMERAL_MAP.get(right, 0)
            return tens * 10 + ones

        return None

    def get_file_extension(self, filename: str) -> str:
        """获取文件扩展名"""
        _, ext = os.path.splitext(filename)
        return ext.lower()

    def is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        ext = self.get_file_extension(filename)
        return ext in self.VIDEO_EXTENSIONS

    def is_subtitle_file(self, filename: str) -> bool:
        """判断是否为字幕文件"""
        ext = self.get_file_extension(filename)
        return ext in self.SUBTITLE_EXTENSIONS

    @staticmethod
    def _contains_keyword(text: str, patterns: List) -> bool:
        if not text:
            return False
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False

    def is_special_content(self, name: str, parent_name: Optional[str] = None) -> bool:
        text = f"{name or ''} {parent_name or ''}"
        return self._contains_keyword(text, self.SPECIAL_KEYWORDS)

    def is_extra_content(self, name: str, parent_name: Optional[str] = None) -> bool:
        text = f"{name or ''} {parent_name or ''}"
        return self._contains_keyword(text, self.EXTRAS_KEYWORDS)

    def is_noise_directory(self, name: str) -> bool:
        return self._contains_keyword(name or "", self.NOISE_DIR_KEYWORDS)

    def sanitize_filename(self, name: str) -> str:
        """
        清理文件名，移除非法字符
        
        Args:
            name: 原始名称
            
        Returns:
            清理后的名称
        """
        # Windows 非法字符 + 夸克网盘 API 不支持的字符（英文方括号和中文方括号）
        # 注意：移除字符后不留空隙
        illegal_chars = r'[<>:"/\\|?*\[\]【】]'
        name = re.sub(illegal_chars, '', name)
        # 多个空格替换为单个
        name = re.sub(r'\s+', ' ', name)
        # 去除首尾空格
        name = name.strip()
        return name

    def sanitize_for_emby(
        self,
        name: str,
        *,
        ascii_only: bool = False,
        keep_brackets: bool = False,
    ) -> str:
        """
        按 Emby v1.6 规范清理名称。

        处理规则：
        - ':' '/' '\\' '|' -> '-'
        - '?' '*' '"' '<' '>' -> 删除
        - 去除首尾空格与尾部 '.'
        - 可选转为 ASCII（去除重音）
        """
        if not name:
            return ""

        text = name
        # Normalize common mojibake tokens before regular sanitization.
        for bad, good in self.GARBLED_REPLACEMENTS.items():
            text = text.replace(bad, good)
        replacements = {
            ":": "-",
            "/": "-",
            "\\": "-",
            "|": "-",
            "?": "",
            "*": "",
            "\"": "",
            "<": "",
            ">": "",
        }
        for src, target in replacements.items():
            text = text.replace(src, target)

        if not keep_brackets:
            text = text.replace("[", "").replace("]", "").replace("【", "").replace("】", "")

        text = re.sub(r"\s+", " ", text).strip()
        text = text.rstrip(" .")
        text = re.sub(r"-{2,}", "-", text)

        if ascii_only:
            text = unicodedata.normalize("NFKD", text)
            text = text.encode("ascii", "ignore").decode("ascii")
            text = re.sub(r"\s+", " ", text).strip()
            text = text.rstrip(" .")

        return text

    def build_media_root_name(
        self,
        title: str,
        year: Optional[int],
        tmdb_id: Optional[int] = None,
        media_type: str = "movie",
    ) -> str:
        """构建媒体根目录名：只有电影才附加 [tmdbid=xxxx] 标签，避免 Emby 将剧集误认为电影"""
        safe_title = self.sanitize_for_emby(title, ascii_only=False)
        if not safe_title:
            safe_title = self.sanitize_for_emby(title, ascii_only=True)
        if not safe_title:
            safe_title = "Unknown Title"
        if year:
            base = f"{safe_title} ({year})"
        else:
            base = safe_title
        if tmdb_id and media_type == "movie":
            return f"{base} [tmdbid={tmdb_id}]"
        return base

    def build_season_folder_name(self, season: int) -> str:
        """构建季目录名：Season XX"""
        return f"Season {season:02d}"

    def build_movie_filename(self, title: str, year: Optional[int], ext: str) -> str:
        """构建电影文件名：Title (Year).ext"""
        safe_title = self.sanitize_for_emby(title, ascii_only=False)
        if not safe_title:
            safe_title = self.sanitize_for_emby(title, ascii_only=True)
        if not safe_title:
            safe_title = "Unknown Title"
        prefix = f"{safe_title} ({year})" if year else safe_title
        return f"{prefix}{ext}"

    def build_episode_filename(
        self,
        title: str,
        year: Optional[int],
        season: int,
        episode: int,
        ext: str,
    ) -> str:
        """构建剧集文件名：Show (Year) - SxxExx.ext"""
        safe_title = self.sanitize_for_emby(title, ascii_only=False)
        if not safe_title:
            safe_title = self.sanitize_for_emby(title, ascii_only=True)
        if not safe_title:
            safe_title = "Unknown Title"
        prefix = f"{safe_title} ({year})" if year else safe_title
        return f"{prefix} - S{season:02d}E{episode:02d}{ext}"

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
        
        base_dir = self._get_category_dirs().get(category, self._get_category_dirs()['movie'])
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
        
        格式: /收藏TV/TV Shows/{Title} ({Year})/第{S}季/{Title} 第{S}季第{E}集 SxxEyy.ext
        
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
        
        season_folder = f"第{season:02d}季"
        
        if episode is not None:
            # 保留 SxxEyy 标记，确保 Emby 能稳定识别集信息。
            new_name = f"{title} 第{season:02d}季第{episode:02d}集 S{season:02d}E{episode:02d}{ext}"
        else:
            # 无法提取集数，保留原文件名
            new_name = original_filename
        
        base_dir = self._get_category_dirs().get(category, self._get_category_dirs()['tv'])
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
