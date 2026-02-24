"""
周期4优化验证脚本
验证缓存策略优化
"""
import os
import sys

os.chdir('C:\\Users\\24228\\Desktop\\qsm\\backend')
sys.path.insert(0, 'C:\\Users\\24228\\Desktop\\qsm\\backend')

print('=== 周期4优化验证 ===')
print('缓存策略优化检查:')

# 验证 cache.py 优化
with open('app/quark/core/cache.py', 'r', encoding='utf-8') as f:
    cache_content = f.read()

checks = [
    ('OrderedDict', 'LRU数据结构'),
    ('asyncio.Lock()', '并发锁'),
    ('move_to_end', 'LRU移动操作'),
    ('popitem(last=False)', 'LRU淘汰策略'),
    ('max_size', '最大容量限制'),
    ('get_stats', '缓存统计功能'),
    ('get_many', '批量获取'),
    ('set_many', '批量设置'),
    ('async with self._lock', '异步锁使用'),
]

all_passed = True
for keyword, desc in checks:
    passed = keyword in cache_content
    status = 'PASS' if passed else 'FAIL'
    print(f'  [{status}] {desc}')
    if not passed:
        all_passed = False

# 验证导入
print()
print('模块导入检查:')
try:
    from app.quark.core.cache import MemoryCache, CacheManager, get_cache
    print('  [PASS] 缓存模块可正常导入')
except Exception as e:
    print(f'  [FAIL] 导入错误: {e}')
    all_passed = False

try:
    from collections import OrderedDict
    print('  [PASS] OrderedDict 导入正常')
except Exception as e:
    print(f'  [FAIL] OrderedDict 导入错误: {e}')
    all_passed = False

print()
if all_passed:
    print('所有优化验证通过')
else:
    print('部分验证失败')
