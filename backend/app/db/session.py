"""
SQLAlchemy 数据库会话管理
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 数据库文件路径
DATA_DIR = Path(__file__).parent.parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "qsm.db"

# SQLite 连接 URL
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# 创建引擎
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 需要此参数
    echo=False,  # 设为 True 可打印 SQL 语句用于调试
)

# 创建 Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 声明基类
Base = declarative_base()


def get_db():
    """
    获取数据库会话的依赖注入函数
    用于 FastAPI 的 Depends
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    初始化数据库，创建所有表
    """
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
