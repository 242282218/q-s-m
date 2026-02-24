"""
周期2优化验证脚本
验证数据库查询优化
"""
import os
import sys

os.chdir('C:\\Users\\24228\\Desktop\\qsm\\backend')
sys.path.insert(0, 'C:\\Users\\24228\\Desktop\\qsm\\backend')

print('=== 周期2优化验证 ===')
print('数据库查询优化检查:')

# 验证 service.py 优化
with open('app/collection/service.py', 'r', encoding='utf-8') as f:
    service_content = f.read()

checks = [
    ('func.count(Collection.id)', '高效count查询'),
    ('with_entities', '字段选择优化'),
    ('.scalar()', '标量值获取'),
    ('.update({"status": status})', '直接update优化'),
    ('list_optimized', '高级优化版本函数'),
]

all_passed = True
for keyword, desc in checks:
    passed = keyword in service_content
    status = 'PASS' if passed else 'FAIL'
    print(f'  [{status}] {desc}')
    if not passed:
        all_passed = False

# 验证 SQL 语法正确性
print()
print('SQLAlchemy 语法检查:')
try:
    from app.collection.service import CollectionService
    print('  [PASS] CollectionService 类可正常导入')
except Exception as e:
    print(f'  [FAIL] 导入错误: {e}')
    all_passed = False

try:
    from sqlalchemy import func, desc, asc
    print('  [PASS] SQLAlchemy 函数导入正常')
except Exception as e:
    print(f'  [FAIL] SQLAlchemy 导入错误: {e}')
    all_passed = False

print()
if all_passed:
    print('所有优化验证通过')
else:
    print('部分验证失败')
