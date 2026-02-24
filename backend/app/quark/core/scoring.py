import re
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class QualityInfo:
    """质量信息"""
    level: str = "低"
    resolution: str = "未知"
    codec: str = "未知"
    score: float = 50.0
    is_4k: bool = False
    is_1080p: bool = False
    is_720p: bool = False
    is_bdmv: bool = False
    is_remux: bool = False
    is_bluray: bool = False
    is_webdl: bool = False
    is_webrip: bool = False
    is_hdr: bool = False
    is_dv: bool = False
    has_cn_sub: bool = False
    has_multi_audio: bool = False


class QualityEvaluator:
    """质量评估器"""
    
    def __init__(self) -> None:
        pass
    
    def evaluate(self, name: str, size_str: Optional[str] = None) -> QualityInfo:
        """评估资源质量"""
        info = QualityInfo()
        
        name_lower = name.lower()
        
        if "2160p" in name_lower or "4k" in name_lower or "uhd" in name_lower:
            info.is_4k = True
            info.resolution = "4K"
        
        if "1080p" in name_lower:
            info.is_1080p = True
            info.resolution = "1080P"
        
        if "720p" in name_lower:
            info.is_720p = True
            info.resolution = "720P"
        
        if "bdmv" in name_lower:
            info.is_bdmv = True
            info.level = "极高"
        elif "remux" in name_lower:
            info.is_remux = True
            info.level = "极高"
        elif "bluray" in name_lower or "蓝光" in name or "原盘" in name:
            info.is_bluray = True
            info.level = "高"
        elif "web-dl" in name_lower or "webdl" in name_lower:
            info.is_webdl = True
            info.level = "中高"
        elif "webrip" in name_lower:
            info.is_webrip = True
            info.level = "中"
        else:
            info.level = "低"
        
        if "hdr" in name_lower or "dv" in name_lower or "杜比视界" in name:
            info.is_hdr = True
            info.is_dv = True
        
        if "x265" in name_lower or "hevc" in name_lower or "h.265" in name_lower:
            info.codec = "H.265"
        elif "x264" in name_lower or "h.264" in name_lower:
            info.codec = "H.264"
        
        if "atmos" in name_lower or "杜比全景声" in name or "dtsx" in name_lower:
            info.codec = "Atmos" if "atmos" in name_lower else "DTS"
        
        if "中字" in name or "字幕" in name or "双语" in name or "国英" in name:
            info.has_cn_sub = True
        if "国英" in name or "双语" in name or "双音" in name:
            info.has_multi_audio = True
        
        if size_str:
            info.score = self._calculate_score(size_str)
        
        return info
    
    def _calculate_score(self, size_str: Optional[str]) -> float:
        """根据文件大小计算分数"""
        if not size_str:
            return 50.0
        
        size_gb = self._parse_size_to_gb(size_str)
        if size_gb is None:
            return 50.0
        
        if size_gb < 0.5:
            return 20.0
        elif size_gb < 1.0:
            return 40.0
        elif size_gb < 5.0:
            return 60.0
        elif size_gb < 10.0:
            return 70.0
        elif size_gb < 20.0:
            return 80.0
        elif size_gb < 50.0:
            return 90.0
        else:
            return 100.0
    
    def _parse_size_to_gb(self, size_str: str) -> Optional[float]:
        """将文件大小字符串转换为 GB"""
        size_str = size_str.lower().strip()
        
        patterns = [
            (r"([\d.]+)\s*(tb|t)", None),
            (r"([\d.]+)\s*(gb|g)", None),
            (r"([\d.]+)\s*(mb|m)", None),
            (r"([\d.]+)\s*(kb|k)", None),
        ]
        
        for pattern in patterns:
            match = re.search(pattern, size_str)
            if match:
                value = float(match.group(1))
                unit = match.group(2)
                if unit in ("tb", "t"):
                    return value * 1024
                elif unit in ("gb", "g"):
                    return value
                elif unit in ("mb", "m"):
                    return value / 1024
                elif unit in ("kb", "k"):
                    return value / (1024 * 1024)
        
        return None


def compute_overall(confidence: float, quality_score: float, confidence_weight: float = 0.7, quality_weight: float = 0.3) -> float:
    """
    计算综合评分
    
    Args:
        confidence: 置信度（0-1）
        quality_score: 画质评分（0-100）
        confidence_weight: 置信度权重
        quality_weight: 画质权重
        
    Returns:
        综合评分（0-100）
    """
    confidence_scaled = confidence * 100
    overall = (confidence_scaled * confidence_weight) + (quality_score * quality_weight)
    return min(overall, 100.0)


def mark_best(results: list) -> None:
    """
    标记最佳结果
    
    Args:
        results: 匹配结果列表
    """
    if not results:
        return
    
    best_result = max(results, key=lambda x: x.overall_score)
    best_result.is_best = True
    
    for result in results:
        if result != best_result:
            result.is_best = False
