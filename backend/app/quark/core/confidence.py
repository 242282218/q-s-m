import re
from typing import Dict, Any


class ConfidenceCalculator:
    """
    置信度计算器，用于计算资源与媒体信息的匹配置信度
    """
    
    def __init__(self):
        self.weights = {
            "exact_title_match": 0.5,
            "title_match": 0.3,
            "partial_title_match": 0.2,
            "year_match": 0.2,
            "episode_match": 0.1,
            "season_match": 0.1,
        }
    
    def calculate(self, resource_title: str, media_info: Any) -> Any:
        """
        计算置信度
        
        Args:
            resource_title: 资源标题
            media_info: 媒体信息
            
        Returns:
            匹配详情对象
        """
        from app.quark.core.models import MatchDetails
        
        md = MatchDetails()
        
        # 清理标题，移除特殊字符
        clean_resource_title = self._clean_title(resource_title)
        clean_media_title = self._clean_title(media_info.title)
        clean_original_title = self._clean_title(media_info.original_title)
        
        # 精确匹配
        if clean_resource_title == clean_media_title or clean_resource_title == clean_original_title:
            md.exact_title_match = True
            md.title_match = True
        # 标题匹配
        elif clean_media_title in clean_resource_title or clean_original_title in clean_resource_title:
            md.title_match = True
        # 部分匹配
        elif self._partial_match(clean_resource_title, clean_media_title) or self._partial_match(clean_resource_title, clean_original_title):
            md.partial_title_match = True
        
        # 年份匹配
        if media_info.year:
            year_pattern = re.compile(rf"\b{media_info.year}\b")
            if year_pattern.search(resource_title):
                md.year_match = True
        
        return md
    
    def _clean_title(self, title: str) -> str:
        """
        清理标题，移除特殊字符和冗余信息
        """
        # 移除HTML标签
        title = re.sub(r'<[^>]+>', '', title)
        # 移除特殊字符，只保留字母、数字、空格和中文字符
        title = re.sub(r'[^a-zA-Z0-9\s\u4e00-\u9fa5]', '', title)
        # 转换为小写
        title = title.lower()
        # 移除多余空格
        title = re.sub(r'\s+', ' ', title).strip()
        # 移除常见的副标题标记
        title = re.sub(r'\s*(?:\(|\[|【).*?(?:\)|\]|】)\s*', '', title)
        return title
    
    def _partial_match(self, text1: str, text2: str) -> bool:
        """
        检查部分匹配
        """
        # 分割成单词
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        # 移除单字符单词
        words1 = {word for word in words1 if len(word) > 1}
        words2 = {word for word in words2 if len(word) > 1}
        
        # 如果有共同单词，返回True
        if words1.intersection(words2):
            return True
        
        return False