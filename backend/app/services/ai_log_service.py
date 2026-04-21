import json
from typing import Any, Dict, List, Optional

from app.db.database import get_connection


def create_ai_conversation_log(
    *,
    feature: str,
    stage: Optional[str],
    model: str,
    request_messages: List[Dict[str, str]],
    status: str = "success",
    run_id: Optional[int] = None,
    recipe_id: Optional[int] = None,
    response_text: Optional[str] = None,
    error_text: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO ai_conversation_logs (
                feature,
                stage,
                model,
                status,
                run_id,
                recipe_id,
                request_messages_json,
                response_text,
                error_text,
                meta_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                feature,
                stage,
                model,
                status,
                run_id,
                recipe_id,
                json.dumps(request_messages, ensure_ascii=False),
                response_text,
                error_text,
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
        return cursor.lastrowid


def list_ai_conversation_logs(
    *,
    limit: int = 50,
    offset: int = 0,
    feature: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))

    where_clauses: List[str] = []
    params: List[Any] = []

    if feature:
        where_clauses.append("feature = ?")
        params.append(feature.strip())

    if status:
        where_clauses.append("status = ?")
        params.append(status.strip())

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    with get_connection() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM ai_conversation_logs {where_sql}",
            params,
        ).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT
                l.id,
                l.feature,
                l.stage,
                l.model,
                l.status,
                l.run_id,
                l.recipe_id,
                r.name AS recipe_name,
                l.response_text,
                l.error_text,
                l.created_at,
                l.updated_at
            FROM ai_conversation_logs AS l
            LEFT JOIN recipes AS r ON r.id = l.recipe_id
            {where_sql}
            ORDER BY l.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, safe_limit, safe_offset],
        ).fetchall()

    return {
        "items": [
            {
                "id": row["id"],
                "feature": row["feature"],
                "stage": row["stage"],
                "model": row["model"],
                "status": row["status"],
                "run_id": row["run_id"],
                "recipe_id": row["recipe_id"],
                "recipe_name": row["recipe_name"],
                "response_preview": (row["response_text"] or "")[:240],
                "error_text": row["error_text"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
        "total": total,
        "limit": safe_limit,
        "offset": safe_offset,
    }


def get_ai_conversation_log(log_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                l.*,
                r.name AS recipe_name
            FROM ai_conversation_logs AS l
            LEFT JOIN recipes AS r ON r.id = l.recipe_id
            WHERE l.id = ?
            """,
            (log_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "feature": row["feature"],
        "stage": row["stage"],
        "model": row["model"],
        "status": row["status"],
        "run_id": row["run_id"],
        "recipe_id": row["recipe_id"],
        "recipe_name": row["recipe_name"],
        "request_messages": _safe_json_loads_list(row["request_messages_json"]),
        "response_text": row["response_text"],
        "error_text": row["error_text"],
        "meta": _safe_json_loads_dict(row["meta_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _safe_json_loads_list(raw_value: Optional[str]) -> List[Dict[str, Any]]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_json_loads_dict(raw_value: Optional[str]) -> Dict[str, Any]:
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
