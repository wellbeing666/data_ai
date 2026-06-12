from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from app.core.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL_PATH = PROJECT_ROOT / "database" / "mysql_schema.sql"
REQUIRED_TABLES = {"users", "auth_sessions", "analysis_conversations"}


def _connection_kwargs(*, with_database: bool = True) -> dict:
    settings = get_settings()
    kwargs: dict = {
        "host": settings.mysql_host,
        "port": int(settings.mysql_port),
        "user": settings.mysql_user,
        "password": settings.mysql_password,
        "charset": settings.mysql_charset,
        "cursorclass": DictCursor,
        "autocommit": False,
        "connect_timeout": int(settings.mysql_connect_timeout),
    }
    if with_database:
        kwargs["database"] = settings.mysql_database
    return kwargs


@contextmanager
def mysql_connection(*, with_database: bool = True) -> Iterator[Connection]:
    conn = pymysql.connect(**_connection_kwargs(with_database=with_database))
    try:
        yield conn
    finally:
        conn.close()


def init_database_schema() -> None:
    settings = get_settings()
    database_name = _safe_database_name(settings.mysql_database)

    with mysql_connection(with_database=False) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()

    with mysql_connection(with_database=True) as conn:
        existing_tables = _get_existing_tables(conn)
        if REQUIRED_TABLES.issubset(existing_tables):
            return

        schema_sql = _load_schema_sql()
        with conn.cursor() as cursor:
            for statement in _split_sql(schema_sql):
                normalized = statement.lstrip().lower()
                if normalized.startswith("create database") or normalized.startswith("use "):
                    continue
                cursor.execute(statement)
        conn.commit()


def _safe_database_name(database_name: str) -> str:
    normalized = str(database_name or "").strip().replace("`", "")
    if not normalized:
        raise RuntimeError("MYSQL_DATABASE 未配置。")
    return normalized


def _load_schema_sql() -> str:
    if not SCHEMA_SQL_PATH.exists():
        raise RuntimeError(f"数据库初始化脚本不存在：{SCHEMA_SQL_PATH}")
    return SCHEMA_SQL_PATH.read_text(encoding="utf-8")


def _get_existing_tables(conn: Connection) -> set[str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            """
        )
        rows = cursor.fetchall()
    return {str(row.get("TABLE_NAME") or row.get("table_name")) for row in rows}


def _split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    previous = ""
    index = 0

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if in_line_comment:
            if char in {"\n", "\r"}:
                in_line_comment = False
                current.append(char)
            index += 1
            previous = char
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                previous = "/"
                continue
            index += 1
            previous = char
            continue

        if not in_single_quote and not in_double_quote:
            if char == "-" and next_char == "-":
                in_line_comment = True
                index += 2
                previous = "-"
                continue
            if char == "#":
                in_line_comment = True
                index += 1
                previous = char
                continue
            if char == "/" and next_char == "*":
                in_block_comment = True
                index += 2
                previous = "*"
                continue

        if char == "'" and previous != "\\" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and previous != "\\" and not in_single_quote:
            in_double_quote = not in_double_quote

        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)

        previous = char
        index += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements
