"""数据库迁移 - 启动时自动检查并补齐缺失的列。

策略：读取 ORM 模型定义的列，与实际 SQLite 表对比，缺失的列自动 ALTER TABLE 添加。
仅支持添加列（SQLite 不支持删除/修改列），安全且幂等。
"""

import logging
import sqlite3
from pathlib import Path

from sqlalchemy import inspect

from db.tables import Base

logger = logging.getLogger(__name__)

# SQLAlchemy type → SQLite type 映射
_TYPE_MAP = {
    "VARCHAR": "TEXT",
    "STRING": "TEXT",
    "TEXT": "TEXT",
    "INTEGER": "INTEGER",
    "FLOAT": "REAL",
    "BOOLEAN": "INTEGER",
    "DATETIME": "TEXT",
}


def _sa_type_to_sqlite(sa_type) -> str:
    """将 SQLAlchemy 列类型转换为 SQLite 类型字符串。"""
    type_name = type(sa_type).__name__.upper()
    return _TYPE_MAP.get(type_name, "TEXT")


def _get_default_clause(column) -> str:
    """获取列的 DEFAULT 子句。"""
    if column.default is not None:
        val = column.default.arg
        if callable(val):
            # 动态默认值（如 uuid），SQLite 不支持，用空字符串
            if _sa_type_to_sqlite(column.type) == "INTEGER":
                return " DEFAULT 0"
            return " DEFAULT ''"
        if isinstance(val, bool):
            return f" DEFAULT {1 if val else 0}"
        if isinstance(val, (int, float)):
            return f" DEFAULT {val}"
        return f" DEFAULT '{val}'"
    if column.nullable:
        return ""
    # NOT NULL 且无默认值，给一个安全默认
    sqlite_type = _sa_type_to_sqlite(column.type)
    if sqlite_type == "INTEGER":
        return " DEFAULT 0"
    if sqlite_type == "REAL":
        return " DEFAULT 0.0"
    return " DEFAULT ''"


def migrate_db(database_url: str) -> list[str]:
    """检查所有 ORM 表，补齐缺失的列。

    Args:
        database_url: SQLite 数据库 URL（如 sqlite:///./data/research.db）

    Returns:
        执行的 ALTER TABLE 语句列表（空列表表示无需迁移）
    """
    db_path = database_url.replace("sqlite:///", "")
    if not Path(db_path).exists():
        logger.info("db_not_exists path=%s skipping_migration", db_path)
        return []

    conn = sqlite3.connect(db_path)
    executed: list[str] = []

    try:
        for table in Base.metadata.sorted_tables:
            table_name = table.name

            # 获取现有列
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {row[1] for row in cursor.fetchall()}

            if not existing_columns:
                # 表不存在，create_all 会处理
                continue

            # 对比 ORM 定义的列
            for column in table.columns:
                if column.name not in existing_columns:
                    sqlite_type = _sa_type_to_sqlite(column.type)
                    default_clause = _get_default_clause(column)
                    sql = (
                        f"ALTER TABLE {table_name} "
                        f"ADD COLUMN {column.name} {sqlite_type}{default_clause}"
                    )
                    conn.execute(sql)
                    executed.append(sql)
                    logger.info("migration_add_column table=%s column=%s", table_name, column.name)

        if executed:
            conn.commit()
            logger.info("migration_completed statements=%d", len(executed))
        else:
            logger.debug("migration_no_changes_needed")

    finally:
        conn.close()

    return executed
