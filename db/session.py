"""数据库引擎和会话管理。"""

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_path = settings.database_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(settings.database_url, echo=False)
        logger.info("db_engine_created url=%s", settings.database_url)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal


def get_session() -> Session:
    factory = get_session_factory()
    return factory()


def init_db() -> None:
    """创建所有表。"""
    from db.tables import Base

    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("db_tables_initialized")
