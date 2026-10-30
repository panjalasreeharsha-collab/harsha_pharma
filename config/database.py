"""MySQL connection configuration loaded from environment variables."""

from __future__ import annotations

import os

import mysql.connector
from dotenv import load_dotenv
from mysql.connector import MySQLConnection


load_dotenv()


def get_connection() -> MySQLConnection:
    """Create a MySQL connection using the MYSQL_* environment variables."""
    required_variables = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_DATABASE")
    missing_variables = [
        variable for variable in required_variables if not os.getenv(variable)
    ]
    if missing_variables:
        raise RuntimeError(
            "Missing required database environment variable(s): "
            + ", ".join(missing_variables)
        )

    try:
        port = int(os.getenv("MYSQL_PORT", "3306"))
    except ValueError as exc:
        raise RuntimeError("MYSQL_PORT must be a valid integer.") from exc

    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        port=port,
        user=os.environ["MYSQL_USER"],
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        collation="utf8mb4_unicode_ci",
        autocommit=False,
    )
