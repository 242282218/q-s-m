import requests
import time

def test_cache():
    print("测试缓存功能...")
    
    # 第一次搜索
    start = time.time()
    result1 = requests.get('http://localhost:7799/api/quark/search/tmdb/299536?media_type=movie').json()
    time1 = time.time() - start
    print(f'第一次搜索耗时: {time1:.3f}秒')
    print(f'结果数量: {result1.get("total", 0)}')
    
    # 第二次搜索（应该从缓存中获取）
    start = time.time()
    result2 = requests.get('http://localhost:7799/api/quark/search/tmdb/299536?media_type=movie').json()
    time2 = time.time() - start
    print(f'第二次搜索耗时: {time2:.3f}秒')
    print(f'结果数量: {result2.get("total", 0)}')
    
    # 比较结果
    if result1 == result2:
        print("✓ 缓存功能正常工作")
    else:
        print("✗ 缓存功能异常")
    
    # 比较响应时间
    if time2 < time1:
        print(f"✓ 缓存加速效果明显（快了 {((time1 - time2) / time1 * 100):.1f}%）")
    else:
        print("✗ 缓存加速效果不明显")

if __name__ == '__main__':
    test_cache()
