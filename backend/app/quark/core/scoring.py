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
    # 将置信度转换为0-100范围
    confidence_scaled = confidence * 100
    
    # 加权计算综合评分
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
    
    # 按综合评分排序，取最高分为最佳
    best_result = max(results, key=lambda x: x.overall_score)
    best_result.is_best = True
    
    # 其他结果设为非最佳
    for result in results:
        if result != best_result:
            result.is_best = False