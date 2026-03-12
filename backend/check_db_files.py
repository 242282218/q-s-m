"""检查数据库文件"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "qsm.db"

print(f"=== 数据库文件信息 ===")
print(f"数据库路径：{DB_PATH.absolute()}")
print(f"数据库文件存在：{DB_PATH.exists()}")
if DB_PATH.exists():
    print(f"数据库文件大小：{DB_PATH.stat().st_size} 字节")

# 检查 WAL 文件
WAL_PATH = Path(__file__).parent / "data" / "qsm.db-wal"
SHM_PATH = Path(__file__).parent / "data" / "qsm.db-shm"
print(f"\nWAL 文件存在：{WAL_PATH.exists()}")
if WAL_PATH.exists():
    print(f"WAL 文件大小：{WAL_PATH.stat().st_size} 字节")
print(f"SHM 文件存在：{SHM_PATH.exists()}")
if SHM_PATH.exists():
    print(f"SHM 文件大小：{SHM_PATH.stat().st_size} 字节")

print(f"\n=== 数据库连接测试 ===")
try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM collections")
    count = cursor.fetchone()[0]
    print(f"数据库连接成功")
    print(f"collections 表记录数：{count}")
    
    # 检查 WAL 模式
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    print(f"日志模式：{journal_mode}")
    
    # 检查 WAL 检查点状态
    cursor.execute("PRAGMA wal_checkpoint(PASSIVE)")
    checkpoint_result = cursor.fetchone()
    print(f"WAL 检查点状态：{checkpoint_result}")
    
    conn.close()
    print(f"\n数据库状态正常")
except Exception as e:
    print(f"数据库连接失败：{e}")
