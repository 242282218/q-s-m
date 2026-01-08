import re
from typing import Optional, Any


class QualityEvaluator:
    """
    质量评估器，用于评估资源的画质质量
    """
    
    def __init__(self):
        # 分辨率匹配模式
        self.resolution_patterns = {
            "8K": re.compile(r"(8K|4320P)", re.IGNORECASE),
            "4K": re.compile(r"(4K|2160P)", re.IGNORECASE),
            "2K": re.compile(r"(2K|1440P)", re.IGNORECASE),
            "1080P": re.compile(r"1080P|FHD", re.IGNORECASE),
            "720P": re.compile(r"720P|HD", re.IGNORECASE),
            "480P": re.compile(r"480P", re.IGNORECASE),
            "360P": re.compile(r"360P", re.IGNORECASE),
        }
        
        # 编解码器匹配模式
        self.codec_patterns = {
            "H.265": re.compile(r"H\.265|HEVC", re.IGNORECASE),
            "H.264": re.compile(r"H\.264|AVC", re.IGNORECASE),
            "MPEG-4": re.compile(r"MPEG-4|MPEG4|XviD|DivX", re.IGNORECASE),
        }
    
    def evaluate(self, name: str, size: str) -> Any:
        """
        评估资源质量
        
        Args:
            name: 资源名称
            size: 资源大小
            
        Returns:
            QualityInfo对象
        """
        from app.quark.core.models import QualityInfo
        
        # 检测分辨率
        resolution = "未知"
        for res, pattern in self.resolution_patterns.items():
            if pattern.search(name):
                resolution = res
                break
        
        # 检测编解码器
        codec = "未知"
        for c, pattern in self.codec_patterns.items():
            if pattern.search(name):
                codec = c
                break
        
        # 计算大小（GB）
        total_size_gb = self._parse_size(size)
        
        # 确定质量等级
        level = self._determine_level(resolution, codec, total_size_gb)
        
        # 检测动态范围
        is_dynamic = bool(re.search(r"HDR|杜比视界|Dolby Vision", name, re.IGNORECASE))
        
        # 检测超高清
        is_uhd = resolution in ["8K", "4K"]
        
        return QualityInfo(
            level=level,
            resolution=resolution,
            codec=codec,
            total_size_gb=total_size_gb,
            size=size,
            is_dynamic=is_dynamic,
            is_uhd=is_uhd,
        )
    
    def _parse_size(self, size_str: str) -> Optional[float]:
        """
        解析文件大小
        """
        if not size_str:
            return None
        
        # 匹配数字和单位
        match = re.match(r"(\d+(?:\.\d+)?)([KMGTP]B)", size_str, re.IGNORECASE)
        if not match:
            return None
        
        size = float(match.group(1))
        unit = match.group(2).upper()
        
        # 转换为GB
        unit_factors = {
            "KB": 1e-6,
            "MB": 1e-3,
            "GB": 1,
            "TB": 1e3,
            "PB": 1e6,
        }
        
        return size * unit_factors[unit]
    
    def _determine_level(self, resolution: str, codec: str, size_gb: Optional[float]) -> str:
        """
        确定质量等级
        """
        if resolution in ["8K", "4K"]:
            return "极高"
        elif resolution == "2K" or (resolution == "1080P" and codec in ["H.265", "H.264"]):
            return "高"
        elif resolution == "1080P":
            return "中高"
        elif resolution == "720P":
            return "中"
        elif resolution in ["480P", "360P"]:
            return "低"
        else:
            return "未知"