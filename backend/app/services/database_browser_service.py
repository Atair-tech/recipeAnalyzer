from typing import Any, Dict, List, Optional

from app.db.database import get_connection


SYSTEM_TABLE_PREFIXES = ("sqlite_", "recipe_search")


def list_database_tables() -> Dict[str, Any]:
    with get_connection() as connection:
        tables = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

        items = []
        for row in tables:
            table_name = row["name"]
            if _is_hidden_table(table_name):
                continue

            column_info = _get_table_columns(connection, table_name)
            row_count = connection.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()["count"]
            items.append(
                {
                    "name": table_name,
                    "row_count": row_count,
                    "column_count": len(column_info),
                    "primary_key": next((item["name"] for item in column_info if item["is_primary_key"]), None),
                }
            )

    return {"items": items}


def get_table_rows(table_name: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    normalized_table_name = _normalize_table_name(table_name)
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)

    with get_connection() as connection:
        allowed_tables = {item["name"] for item in list_database_tables()["items"]}
        if normalized_table_name not in allowed_tables:
            raise ValueError("Unknown table")

        columns = _get_table_columns(connection, normalized_table_name)
        order_column = _resolve_order_column(columns)
        total_rows = connection.execute(
            f'SELECT COUNT(*) AS count FROM "{normalized_table_name}"'
        ).fetchone()["count"]

        query = f'SELECT * FROM "{normalized_table_name}"'
        if order_column:
            query += f' ORDER BY "{order_column}"'
        query += " LIMIT ? OFFSET ?"

        rows = connection.execute(query, (safe_limit, safe_offset)).fetchall()

    return {
        "table_name": normalized_table_name,
        "total_rows": total_rows,
        "limit": safe_limit,
        "offset": safe_offset,
        "columns": columns,
        "items": [dict(row) for row in rows],
    }


def _get_table_columns(connection, table_name: str) -> List[Dict[str, Any]]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [
        {
            "name": row["name"],
            "type": row["type"] or "TEXT",
            "is_nullable": not bool(row["notnull"]),
            "default_value": row["dflt_value"],
            "is_primary_key": bool(row["pk"]),
        }
        for row in rows
    ]


def _resolve_order_column(columns: List[Dict[str, Any]]) -> Optional[str]:
    primary_key = next((item["name"] for item in columns if item["is_primary_key"]), None)
    if primary_key:
        return primary_key

    for candidate in ("created_at", "id", "name"):
        if any(item["name"] == candidate for item in columns):
            return candidate

    return columns[0]["name"] if columns else None


def _normalize_table_name(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("Missing table name")
    return normalized


def _is_hidden_table(table_name: str) -> bool:
    return table_name.startswith(SYSTEM_TABLE_PREFIXES)
