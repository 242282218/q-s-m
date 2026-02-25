"""
优化验证测试
验证前端优化是否正确实施
"""
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_dummy():
    """基础测试"""
    assert True


def test_collection_js_syntax():
    """验证 collection.js 关键函数存在"""
    js_path = ROOT_DIR / "app" / "static" / "js" / "collection.js"
    with open(js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 验证关键函数存在
    assert "renderCardsBatch" in content, "renderCardsBatch 函数不存在"
    assert "createCardElement" in content, "createCardElement 函数不存在"
    assert "initEventDelegation" in content, "initEventDelegation 函数不存在"
    assert "fetchMissingPosters" in content, "fetchMissingPosters 函数不存在"
    assert "buildImageUrl" in content, "buildImageUrl 函数不存在"
    assert "getResponsiveImageSize" in content, "getResponsiveImageSize 函数不存在"

    # 验证优化特性
    assert "DocumentFragment" in content, "DocumentFragment 未使用"
    assert "IntersectionObserver" in content, "IntersectionObserver 未使用"
    assert 'loading="lazy"' in content, "图片懒加载未启用"
    assert 'decoding="async"' in content, "异步解码未启用"
    assert "data-action" in content, "事件委托 data-action 未使用"


def test_css_optimizations():
    """验证 CSS 优化"""
    css_path = ROOT_DIR / "app" / "static" / "css" / "main.css"
    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 验证 CSS 优化
    assert "will-change: transform" in content, "will-change 优化未应用"
    assert "contain: layout style" in content, "contain 优化未应用"
