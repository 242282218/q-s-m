"""
SQLAlchemy 数据库会话管理 - 性能优化版本

优化记录:
- 2026-02-26: 添加连接池配置、性能监控、批量操作支持
"""
import os
import time
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional, List, Any, Dict

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "qsm.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# 性能监控：查询耗时统计
class QueryStats:
    """SQL查询性能统计"""
    def __init__(self):
        self.query_count = 0
        self.total_time = 0.0
        self.slow_queries: List[Dict[str, Any]] = []
    
    def record(self, duration: float, statement: str):
        self.query_count += 1
        self.total_time += duration
        if duration > 0.5:  # 记录慢查询 (>500ms)
            self.slow_queries.append(
                {
                    "duration": round(duration, 3),
                    "statement": statement[:200],
                }
            )
            if len(self.slow_queries) > 100:
                self.slow_queries.pop(0)

query_stats = QueryStats()

# 根据环境选择连接池类型
# 开发环境使用 StaticPool，生产环境使用 QueuePool
is_production = os.getenv("ENV", "development") == "production"

if is_production:
    # 生产环境：使用 QueuePool 支持多线程
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # 自动检测断开的连接
        pool_recycle=3600,   # 1小时后回收连接
        echo=False,
    )
else:
    # 开发环境：使用 StaticPool
    engine = create_engine(
        DATABASE_URL,
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
        poolclass=StaticPool,
        echo=False,
    )

# 启用 WAL 模式以提升并发性能
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
    conn.execute(text("PRAGMA busy_timeout=30000"))
    conn.commit()
    logger.info("SQLite WAL mode enabled")

# 添加查询性能监控
@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.time()

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    duration = time.time() - context._query_start_time
    query_stats.record(duration, statement)
    
    # 记录慢查询警告
    if duration > 1.0:
        logger.warning(f"慢查询 detected: {duration:.3f}s - {statement[:100]}...")

# 创建 Session 工厂 - 优化配置
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # 优化：提交后不立即过期对象
)

# 声明基类
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库会话的依赖注入函数
    用于 FastAPI 的 Depends
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    数据库会话上下文管理器
    用于非 FastAPI 依赖注入场景
    
    用法:
        with get_db_context() as db:
            result = db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise e
    finally:
        db.close()


def init_db():
    """
    初始化数据库，创建所有表
    """
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


def get_query_stats() -> Dict[str, Any]:
    """获取查询统计信息"""
    return {
        "total_queries": query_stats.query_count,
        "total_time": round(query_stats.total_time, 3),
        "avg_time": round(query_stats.total_time / max(query_stats.query_count, 1), 3),
        "slow_queries_count": len(query_stats.slow_queries),
        "recent_slow_queries": query_stats.slow_queries[-10:] if query_stats.slow_queries else []
    }


def reset_query_stats():
    """重置查询统计"""
    query_stats.query_count = 0
    query_stats.total_time = 0.0
    query_stats.slow_queries = []


class BulkInserter:
    """
    批量插入优化器
    
    用法:
        with BulkInserter(db, batch_size=100) as inserter:
            for item in items:
                inserter.add(Model(**item))
    """
    def __init__(self, session: Session, batch_size: int = 100):
        self.session = session
        self.batch_size = batch_size
        self.buffer: List[Any] = []
        self.total_inserted = 0
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.buffer:
            self._flush()
        return False
    
    def add(self, obj: Any):
        """添加对象到缓冲区"""
        self.buffer.append(obj)
        if len(self.buffer) >= self.batch_size:
            self._flush()
    
    def _flush(self):
        """执行批量插入"""
        if not self.buffer:
            return
        
        try:
            self.session.bulk_save_objects(self.buffer)
            self.session.commit()
            self.total_inserted += len(self.buffer)
            self.buffer = []
        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Bulk insert failed: {e}")
            raise


def bulk_insert(session: Session, objects: List[Any], batch_size: int = 100) -> int:
    """
    批量插入对象
    
    Args:
        session: 数据库会话
        objects: 要插入的对象列表
        batch_size: 每批插入数量
        
    Returns:
        成功插入的数量
    """
    if not objects:
        return 0
    
    total = 0
    for i in range(0, len(objects), batch_size):
        batch = objects[i:i + batch_size]
        try:
            session.bulk_save_objects(batch)
            session.commit()
            total += len(batch)
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Batch insert failed at offset {i}: {e}")
            raise
    
    return total
