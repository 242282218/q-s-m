import sys
sys.path.insert(0, 'backend')

from app.config import get_settings

def test_config():
    print("测试配置文件...")
    
    settings = get_settings()
    
    print("\nTMDB配置:")
    print(f"  TMDB_API_KEY: {settings.tmdb_api_key[:10]}..." if len(settings.tmdb_api_key) > 10 else f"  TMDB_API_KEY: {settings.tmdb_api_key}")
    print(f"  DEFAULT_LANG: {settings.default_language}")
    print(f"  TMDB_API_BASE: {settings.tmdb_api_base}")
    print(f"  TMDB_IMAGE_BASE: {settings.tmdb_image_base}")
    
    print("\n夸克搜索配置:")
    print(f"  QUARK_SEARCH_API_PREFIX: {settings.quark_search_api_prefix}")
    print(f"  QUARK_SEARCH_BASE_URL: {settings.quark_search_base_url}")
    print(f"  QUARK_SEARCH_MAX_RETRIES: {settings.quark_search_max_retries}")
    print(f"  QUARK_SEARCH_RATE_LIMIT: {settings.quark_search_rate_limit}")
    print(f"  QUARK_SEARCH_TIMEOUT: {settings.quark_search_timeout}")
    print(f"  QUARK_SEARCH_CONFIDENCE_WEIGHT: {settings.quark_search_confidence_weight}")
    print(f"  QUARK_SEARCH_QUALITY_WEIGHT: {settings.quark_search_quality_weight}")
    print(f"  QUARK_SEARCH_MAX_RESULTS: {settings.quark_search_max_results}")
    
    print("\n缓存配置:")
    print(f"  CACHE_ENABLED: {settings.cache_enabled}")
    print(f"  CACHE_TYPE: {settings.cache_type}")
    print(f"  REDIS_URL: {settings.redis_url}")
    print(f"  CACHE_TTL: {settings.cache_ttl}")
    
    print("\n✓ 配置加载成功")

if __name__ == '__main__':
    test_config()
