"""
测试慢查询监控功能
"""
import sys
import time
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import get_db_context, get_slow_query_stats, set_slow_query_threshold
from app.db.models import Collection
from sqlalchemy import text

def test_slow_query_monitoring():
    """测试慢查询监控"""
    print("=" * 60)
    print("慢查询监控功能测试")
    print("=" * 60)
    
    # 1. 获取当前慢查询统计
    print("\n1. 当前慢查询统计:")
    stats = get_slow_query_stats()
    print(f"   - 慢查询数量：{stats['count']}")
    print(f"   - 平均耗时：{stats['avg_duration']}s")
    print(f"   - 最慢查询：{stats['max_duration']}s")
    
    # 2. 设置慢查询阈值为 0.001 秒（1 毫秒）以便测试
    print("\n2. 设置慢查询阈值为 0.001 秒...")
    set_slow_query_threshold(0.001)
    
    # 3. 执行一个查询
    print("\n3. 执行数据库查询...")
    with get_db_context() as db:
        start = time.time()
        results = db.query(Collection).limit(5).all()
        duration = time.time() - start
        print(f"   - 查询耗时：{duration:.4f}秒")
        print(f"   - 返回结果数：{len(results)}")
    
    # 4. 再次获取慢查询统计
    print("\n4. 查询后的慢查询统计:")
    stats = get_slow_query_stats()
    print(f"   - 慢查询数量：{stats['count']}")
    print(f"   - 平均耗时：{stats['avg_duration']}s")
    print(f"   - 最慢查询：{stats['max_duration']}s")
    
    if stats['count'] > 0:
        print(f"\n✓ 慢查询监控正常工作！检测到 {stats['count']} 个慢查询")
        if stats['queries']:
            print(f"   最近慢查询示例:")
            for q in stats['queries'][:3]:
                print(f"   - 耗时：{q['duration']}s, SQL: {q['statement'][:100]}...")
    else:
        print(f"\n✓ 查询速度快于阈值，未检测到慢查询")
    
    # 5. 恢复默认阈值
    print("\n5. 恢复慢查询阈值为 1.0 秒...")
    set_slow_query_threshold(1.0)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_slow_query_monitoring()
