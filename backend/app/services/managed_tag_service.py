import hashlib
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

from app.db.database import get_connection
from app.services.ai_log_service import create_ai_conversation_log
from app.services.ollama_service import OLLAMA_DEFAULT_MODEL, _call_ollama_chat as _ollama_chat_impl


_job_lock = threading.Lock()
_job_state = {
    "run_id": None,
    "thread": None,
    "pause_requested": False,
}

TAG_PROMPT_VERSION = "managed-tag-v6-string-array-compatible"
MAX_TAGS_PER_RECIPE = 3
MIN_TAG_CONFIDENCE = 0.72
TAG_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "confidence", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["tags"],
    "additionalProperties": False,
}


def _call_ollama_chat(
    model_name: str,
    messages: List[Dict[str, str]],
    *,
    response_format: Optional[Any] = None,
    max_attempts: int = 1,
) -> str:
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            return _ollama_chat_impl(
                model_name,
                messages,
                response_format=response_format,
                extra_options={"temperature": 0.1, "num_ctx": 2048, "num_predict": 1536},
            )
        except Exception as error:
            last_error = error
            if "timed out" not in str(error).lower() or attempt >= max_attempts:
                raise
            time.sleep(0.5)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Ollama call failed without an error")


def list_managed_tags() -> Dict[str, Any]:
    with get_connection() as connection:
        tag_rows = connection.execute(
            """
            SELECT
                mt.id,
                mt.name,
                mt.description,
                mt.is_active,
                mt.sort_order,
                mt.created_at,
                mt.updated_at,
                COUNT(rmt.id) AS recipe_count
            FROM managed_tags AS mt
            LEFT JOIN recipe_managed_tags AS rmt ON rmt.managed_tag_id = mt.id
            GROUP BY mt.id
            ORDER BY mt.sort_order, mt.id
            """
        ).fetchall()
        run_summary = _load_latest_run(connection)

    return {
        "items": [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "is_active": bool(row["is_active"]),
                "sort_order": row["sort_order"],
                "recipe_count": row["recipe_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in tag_rows
        ],
        "run": run_summary,
    }


def create_managed_tag(name: str, description: str = "", is_active: bool = True, sort_order: int = 0) -> Dict[str, Any]:
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Tag name is required")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO managed_tags (name, description, is_active, sort_order, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (normalized_name, (description or "").strip(), 1 if is_active else 0, sort_order),
        )
        tag_id = cursor.lastrowid
        connection.commit()
        return _load_managed_tag(connection, tag_id)


def update_managed_tag(tag_id: int, name: str, description: str = "", is_active: bool = True, sort_order: int = 0) -> Dict[str, Any]:
    normalized_name = (name or "").strip()
    if not normalized_name:
        raise ValueError("Tag name is required")

    with get_connection() as connection:
        existing = connection.execute("SELECT id FROM managed_tags WHERE id = ?", (tag_id,)).fetchone()
        if existing is None:
            raise ValueError("Managed tag not found")

        connection.execute(
            """
            UPDATE managed_tags
            SET
                name = ?,
                description = ?,
                is_active = ?,
                sort_order = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (normalized_name, (description or "").strip(), 1 if is_active else 0, sort_order, tag_id),
        )
        connection.commit()
        return _load_managed_tag(connection, tag_id)


def delete_managed_tag(tag_id: int) -> bool:
    with get_connection() as connection:
        existing = connection.execute("SELECT id FROM managed_tags WHERE id = ?", (tag_id,)).fetchone()
        if existing is None:
            return False
        connection.execute("DELETE FROM managed_tags WHERE id = ?", (tag_id,))
        connection.commit()
        return True


def list_managed_tag_recipes(tag_id: int, search: str = "", limit: int = 100) -> Dict[str, Any]:
    normalized_search = (search or "").strip()
    safe_limit = max(1, min(int(limit), 200))

    with get_connection() as connection:
        tag = connection.execute(
            """
            SELECT id, name, description, is_active, sort_order
            FROM managed_tags
            WHERE id = ?
            """,
            (tag_id,),
        ).fetchone()
        if tag is None:
            raise ValueError("Managed tag not found")

        params: List[Any] = [tag_id]
        search_sql = ""
        if normalized_search:
            search_sql = """
            AND (
                r.name LIKE ?
                OR COALESCE(r.library_section, '') LIKE ?
                OR COALESCE(r.section_name, '') LIKE ?
            )
            """
            pattern = f"%{normalized_search}%"
            params.extend([pattern, pattern, pattern])

        params.append(safe_limit)
        rows = connection.execute(
            f"""
            SELECT
                r.id AS recipe_id,
                r.name,
                r.library_section,
                r.section_name,
                r.record_kind,
                rmt.confidence,
                rmt.reason,
                rmt.updated_at
            FROM recipe_managed_tags AS rmt
            INNER JOIN recipes AS r ON r.id = rmt.recipe_id
            WHERE rmt.managed_tag_id = ?
            {search_sql}
            ORDER BY rmt.updated_at DESC, r.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return {
        "tag": {
            "id": tag["id"],
            "name": tag["name"],
            "description": tag["description"] or "",
            "is_active": bool(tag["is_active"]),
            "sort_order": tag["sort_order"],
        },
        "items": [
            {
                "recipe_id": row["recipe_id"],
                "name": row["name"],
                "library_section": row["library_section"] or "",
                "section_name": row["section_name"] or "",
                "record_kind": row["record_kind"],
                "confidence": row["confidence"],
                "reason": row["reason"] or "",
                "updated_at": row["updated_at"],
            }
            for row in rows
        ],
    }


def remove_managed_tag_assignment(tag_id: int, recipe_id: int) -> Dict[str, Any]:
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id
            FROM recipe_managed_tags
            WHERE managed_tag_id = ? AND recipe_id = ?
            """,
            (tag_id, recipe_id),
        ).fetchone()
        if existing is None:
            raise ValueError("Tag assignment not found")

        connection.execute(
            """
            DELETE FROM recipe_managed_tags
            WHERE managed_tag_id = ? AND recipe_id = ?
            """,
            (tag_id, recipe_id),
        )
        connection.commit()

    return {"deleted": True, "tag_id": tag_id, "recipe_id": recipe_id}


def get_tagging_status() -> Dict[str, Any]:
    with get_connection() as connection:
        run = _load_latest_run(connection)
    with _job_lock:
        is_running = bool(_job_state["thread"] and _job_state["thread"].is_alive())
        pause_requested = bool(_job_state["pause_requested"])
    return {
        "run": run,
        "is_running": is_running,
        "pause_requested": pause_requested,
    }


def start_tagging_run(model: Optional[str] = None) -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("A tagging run is already in progress")

    model_name = (model or OLLAMA_DEFAULT_MODEL).strip()

    with get_connection() as connection:
        total_count = connection.execute(
            "SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'"
        ).fetchone()[0]
        tag_version = _build_tag_version(connection)
        cursor = connection.execute(
            """
            INSERT INTO ai_tagging_runs (
                model,
                status,
                total_count,
                tag_version,
                started_at,
                updated_at
            )
            VALUES (?, 'running', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (model_name, total_count, tag_version),
        )
        run_id = cursor.lastrowid
        connection.commit()

    thread = threading.Thread(
        target=_run_tagging_job,
        args=(run_id, model_name, tag_version),
        daemon=True,
        name=f"recipe-tagging-{run_id}",
    )
    with _job_lock:
        _job_state["run_id"] = run_id
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_tagging_status()


def pause_tagging_run() -> Dict[str, Any]:
    with _job_lock:
        if not (_job_state["thread"] and _job_state["thread"].is_alive()):
            return get_tagging_status()
        _job_state["pause_requested"] = True
    return get_tagging_status()


def resume_tagging_run() -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("A tagging run is already in progress")

    with get_connection() as connection:
        run = connection.execute(
            """
            SELECT id, model, tag_version, status
            FROM ai_tagging_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if run is None or run["status"] != "paused":
        raise ValueError("No paused tagging run available")

    thread = threading.Thread(
        target=_run_tagging_job,
        args=(run["id"], run["model"], run["tag_version"]),
        daemon=True,
        name=f"recipe-tagging-{run['id']}",
    )
    with _job_lock:
        _job_state["run_id"] = run["id"]
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_tagging_status()


def _should_skip_recipe_tagging(
    recipe_id: int,
    source_hash: str,
    model_name: str,
    tag_version: str,
) -> bool:
    with get_connection() as connection:
        state_row = connection.execute(
            """
            SELECT source_hash, model, tag_version, last_error
            FROM recipe_ai_tag_state
            WHERE recipe_id = ?
            """,
            (recipe_id,),
        ).fetchone()

    return bool(
        state_row is not None
        and (state_row["source_hash"] or "") == (source_hash or "")
        and state_row["model"] == model_name
        and state_row["tag_version"] == tag_version
        and not (state_row["last_error"] or "").strip()
    )


def _run_tagging_job(run_id: int, model_name: str, tag_version: str) -> None:
    try:
        with get_connection() as connection:
            active_tags = _load_active_tags(connection)
            recipes = connection.execute(
                """
                SELECT id, name, source_hash
                FROM recipes
                WHERE record_kind = 'recipe'
                ORDER BY id
                """
            ).fetchall()

        pending_recipes = []
        skipped_count = 0
        for recipe_row in recipes:
            recipe_id = int(recipe_row["id"])
            source_hash = recipe_row["source_hash"] or ""
            if _should_skip_recipe_tagging(recipe_id, source_hash, model_name, tag_version):
                skipped_count += 1
            else:
                pending_recipes.append(recipe_row)

        processed_count = 0
        tagged_count = 0
        error_count = 0
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET
                    status = 'running',
                    total_count = ?,
                    processed_count = ?,
                    tagged_count = ?,
                    skipped_count = ?,
                    error_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (len(pending_recipes), processed_count, tagged_count, skipped_count, error_count, run_id),
            )
            connection.commit()

        for row in pending_recipes:
            with _job_lock:
                pause_requested = bool(_job_state["pause_requested"])

            if pause_requested:
                with get_connection() as connection:
                    connection.execute(
                        """
                        UPDATE ai_tagging_runs
                        SET status = 'paused', updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (run_id,),
                    )
                    connection.commit()
                return

            recipe_id = row["id"]
            source_hash = row["source_hash"]
            try:
                if _should_skip_recipe_tagging(recipe_id, source_hash or "", model_name, tag_version):
                    skipped_count += 1
                else:
                    snapshot = _load_recipe_snapshot(recipe_id)
                    selected_tags = _generate_tags_for_recipe(
                        snapshot,
                        active_tags,
                        model_name,
                        run_id=run_id,
                    )
                    with get_connection() as connection:
                        _replace_recipe_managed_tags(connection, recipe_id, selected_tags)
                        connection.execute(
                            """
                            INSERT INTO recipe_ai_tag_state (
                                recipe_id,
                                source_hash,
                                model,
                                tag_version,
                                tagged_at,
                                last_run_id,
                                last_error
                            )
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, NULL)
                            ON CONFLICT(recipe_id) DO UPDATE SET
                                source_hash = excluded.source_hash,
                                model = excluded.model,
                                tag_version = excluded.tag_version,
                                tagged_at = CURRENT_TIMESTAMP,
                                last_run_id = excluded.last_run_id,
                                last_error = NULL
                            """,
                            (recipe_id, source_hash, model_name, tag_version, run_id),
                        )
                        connection.commit()
                    tagged_count += 1
            except Exception as error:
                error_count += 1
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO recipe_ai_tag_state (
                            recipe_id,
                            source_hash,
                            model,
                            tag_version,
                            tagged_at,
                            last_run_id,
                            last_error
                        )
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                        ON CONFLICT(recipe_id) DO UPDATE SET
                            source_hash = excluded.source_hash,
                            model = excluded.model,
                            tag_version = excluded.tag_version,
                            tagged_at = CURRENT_TIMESTAMP,
                            last_run_id = excluded.last_run_id,
                            last_error = excluded.last_error
                        """,
                        (recipe_id, source_hash, model_name, tag_version, run_id, str(error)),
                    )
                    connection.commit()

            processed_count += 1
            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE ai_tagging_runs
                    SET
                        status = 'running',
                        processed_count = ?,
                        tagged_count = ?,
                        skipped_count = ?,
                        error_count = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (processed_count, tagged_count, skipped_count, error_count, run_id),
                )
                connection.commit()

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET
                    status = 'completed',
                    processed_count = total_count,
                    tagged_count = ?,
                    skipped_count = ?,
                    error_count = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (tagged_count, skipped_count, error_count, run_id),
            )
            connection.commit()
    except Exception as error:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET
                    status = 'failed',
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
                """,
                (str(error), run_id),
            )
            connection.commit()
    finally:
        with _job_lock:
            _job_state["thread"] = None
            _job_state["pause_requested"] = False


def _load_latest_run(connection) -> Optional[Dict[str, Any]]:
    row = connection.execute(
        """
        SELECT
            id,
            model,
            status,
            total_count,
            processed_count,
            tagged_count,
            skipped_count,
            error_count,
            tag_version,
            started_at,
            updated_at,
            completed_at,
            error_message
        FROM ai_tagging_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _load_managed_tag(connection, tag_id: int) -> Dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            mt.id,
            mt.name,
            mt.description,
            mt.is_active,
            mt.sort_order,
            mt.created_at,
            mt.updated_at,
            COUNT(rmt.id) AS recipe_count
        FROM managed_tags AS mt
        LEFT JOIN recipe_managed_tags AS rmt ON rmt.managed_tag_id = mt.id
        WHERE mt.id = ?
        GROUP BY mt.id
        """,
        (tag_id,),
    ).fetchone()
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "is_active": bool(row["is_active"]),
        "sort_order": row["sort_order"],
        "recipe_count": row["recipe_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _load_active_tags(connection) -> List[Dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, name, description, sort_order
        FROM managed_tags
        WHERE is_active = 1
        ORDER BY sort_order, id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _build_tag_version(connection) -> str:
    rows = connection.execute(
        """
        SELECT name, description, is_active, sort_order
        FROM managed_tags
        ORDER BY sort_order, id
        """
    ).fetchall()
    serialized = json.dumps(
        {
            "version": TAG_PROMPT_VERSION,
            "tags": [dict(row) for row in rows],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _load_recipe_snapshot(recipe_id: int) -> Dict[str, Any]:
    with get_connection() as connection:
        recipe_row = connection.execute(
            """
            SELECT
                id,
                name,
                library_section,
                section_name,
                cuisine,
                sub_cuisine,
                ingredients_text,
                seasonings_text,
                steps_text,
                notes_text,
                source_reference
            FROM recipes
            WHERE id = ?
            """,
            (recipe_id,),
        ).fetchone()
        ingredient_rows = connection.execute(
            """
            SELECT i.normalized_name AS ingredient_name
            FROM recipe_ingredients AS ri
            INNER JOIN ingredients AS i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY ri.id
            """,
            (recipe_id,),
        ).fetchall()

    return {
        "id": recipe_row["id"],
        "name": recipe_row["name"],
        "library_section": recipe_row["library_section"] or "",
        "section_name": recipe_row["section_name"] or "",
        "cuisine": recipe_row["cuisine"] or "",
        "sub_cuisine": recipe_row["sub_cuisine"] or "",
        "ingredients_text": recipe_row["ingredients_text"] or "",
        "seasonings_text": recipe_row["seasonings_text"] or "",
        "steps_text": recipe_row["steps_text"] or "",
        "notes_text": recipe_row["notes_text"] or "",
        "source_reference": recipe_row["source_reference"] or "",
        "ingredients": [row["ingredient_name"] for row in ingredient_rows],
    }


def _generate_tags_for_recipe(
    recipe: Dict[str, Any],
    tags: List[Dict[str, Any]],
    model_name: str,
    run_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    prompt_lines = [
        "请从给定标签中为菜谱挑选最合适的 0-5 个标签。",
        "只能从候选标签里选，不要创造新标签。",
        "输出必须是合法 JSON，不要输出 markdown。",
        "JSON 格式：",
        '{ "tags": [ { "name": "标签名", "confidence": 0.0, "reason": "一句理由" } ] }',
        "",
        "候选标签：",
    ]
    for item in tags:
        prompt_lines.append(f"- {item['name']}：{item['description'] or ''}")

    prompt_lines.extend(
        [
            "",
            "菜谱信息：",
            f"菜名：{recipe['name']}",
            f"专题库：{recipe['library_section']}",
            f"分组：{recipe['section_name']}",
            f"菜系：{recipe['cuisine']} / {recipe['sub_cuisine']}",
            f"食材：{recipe['ingredients_text']}",
            f"调料：{recipe['seasonings_text']}",
            f"做法：{recipe['steps_text']}",
            f"备注：{recipe['notes_text']}",
            f"来源备注：{recipe['source_reference']}",
        ]
    )

    messages = [
        {
            "role": "system",
            "content": "你是菜谱标签分类器。请严格输出 JSON。",
        },
        {
            "role": "user",
            "content": "\n".join(prompt_lines),
        },
    ]

    try:
        raw_content = _call_ollama_chat(model_name, messages)
    except Exception as error:
        create_ai_conversation_log(
            feature="managed_tagging",
            stage="tagging",
            model=model_name,
            request_messages=messages,
            status="error",
            run_id=run_id,
            recipe_id=recipe["id"],
            error_text=str(error),
            meta={"recipe_name": recipe["name"]},
        )
        raise

    create_ai_conversation_log(
        feature="managed_tagging",
        stage="tagging",
        model=model_name,
        request_messages=messages,
        status="success",
        run_id=run_id,
        recipe_id=recipe["id"],
        response_text=raw_content,
        meta={"recipe_name": recipe["name"]},
    )

    parsed = _extract_json_object(raw_content)
    tag_items = parsed.get("tags", [])
    if not isinstance(tag_items, list):
        return []

    allowed_names = {item["name"] for item in tags}
    selected: List[Dict[str, Any]] = []
    seen = set()
    for item in tag_items:
        name = str((item or {}).get("name", "")).strip()
        if not name or name not in allowed_names or name in seen:
            continue
        seen.add(name)
        try:
            confidence = float((item or {}).get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        if confidence <= 0:
            confidence = 0.6
        selected.append(
            {
                "name": name,
                "confidence": max(0.0, min(confidence, 1.0)),
                "reason": str((item or {}).get("reason", "")).strip(),
            }
        )
    return selected[:5]


def _replace_recipe_managed_tags(connection, recipe_id: int, selected_tags: List[Dict[str, Any]]) -> None:
    connection.execute("DELETE FROM recipe_managed_tags WHERE recipe_id = ?", (recipe_id,))
    if not selected_tags:
        return

    tag_rows = connection.execute("SELECT id, name FROM managed_tags").fetchall()
    tag_id_map = {row["name"]: row["id"] for row in tag_rows}
    for item in selected_tags:
        tag_id = tag_id_map.get(item["name"])
        if tag_id is None:
            continue
        connection.execute(
            """
            INSERT INTO recipe_managed_tags (
                recipe_id,
                managed_tag_id,
                source,
                confidence,
                reason,
                updated_at
            )
            VALUES (?, ?, 'ai', ?, ?, CURRENT_TIMESTAMP)
            """,
            (recipe_id, tag_id, item["confidence"], item["reason"]),
        )


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON object not found")

    return json.loads(cleaned[start : end + 1])


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.replace("json", "", 1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"tags": parsed}
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    last_payload: Optional[Dict[str, Any]] = None
    for index, char in enumerate(cleaned):
        if char not in "{[":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            last_payload = parsed
        elif isinstance(parsed, list):
            last_payload = {"tags": parsed}

    if last_payload is not None:
        return last_payload

    raise ValueError("JSON payload not found")


def _supports_tag(recipe: Dict[str, Any], tag_name: str) -> bool:
    name = str(recipe.get("name") or "")
    section_name = str(recipe.get("section_name") or "")
    ingredients_text = str(recipe.get("ingredients_text") or "")
    seasonings_text = str(recipe.get("seasonings_text") or "")
    steps_text = str(recipe.get("steps_text") or "")
    notes_text = str(recipe.get("notes_text") or "")
    combined = " ".join([name, section_name, ingredients_text, seasonings_text, steps_text, notes_text]).lower()

    staple_like = any(token in name for token in ("饭", "面", "粉", "米线", "粿", "通心粉", "意面", "面片"))
    has_serve_with_rice_cue = any(token in combined for token in ("下饭", "配饭", "拌饭酱", "盖饭"))

    strict_rules = {
        "下饭": (not staple_like) or has_serve_with_rice_cue,
        "一锅出": any(token in combined for token in ("一锅", "同锅", "一锅到底", "焖饭", "煲仔饭", "炖饭", "烩饭")),
        "快手": any(token in combined for token in ("快手", "快速", "几分钟", "简单", "省时")),
        "便当友好": any(token in combined for token in ("便当", "带饭", "复热", "隔夜")),
        "宴客": any(token in combined for token in ("宴客", "待客", "招待", "聚餐", "请客", "正式上桌")),
        "早餐友好": any(token in combined for token in ("早餐", "早午餐")),
        "凉拌": any(token in combined for token in ("凉拌", "冷盘", "凉菜", "沙拉", "冷却后拌")),
        "蒸制": any(token in combined for token in ("蒸", "蒸锅", "蒸箱")),
        "汤羹": any(token in combined for token in ("汤", "羹", "高汤", "清汤", "浓汤")),
    }
    return strict_rules.get(tag_name, True)


def _generate_tags_for_recipe(
    recipe: Dict[str, Any],
    tags: List[Dict[str, Any]],
    model_name: str,
    run_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    compact_recipe = {
        "name": recipe.get("name", ""),
        "library_section": recipe.get("library_section", ""),
        "section_name": recipe.get("section_name", ""),
        "cuisine": recipe.get("cuisine", ""),
        "sub_cuisine": recipe.get("sub_cuisine", ""),
        "ingredients_text": recipe.get("ingredients_text", ""),
        "seasonings_text": recipe.get("seasonings_text", ""),
        "notes_text": recipe.get("notes_text", ""),
        "structured_ingredients": recipe.get("ingredients", []),
    }
    prompt_lines = [
        "/no_think",
        "Do not output thinking, analysis, explanation, or chain-of-thought.",
        "Output the final JSON object immediately.",
        "",
        "Select the 0-3 most suitable tags for this recipe from the candidate tags.",
        "Use only candidate tags. Do not invent new tags.",
        "Be conservative. If uncertain, omit the tag.",
        "Do not assign broad tags by default.",
        "Do not assign '下饭' only because the dish itself is a rice or noodle dish.",
        "Do not assign '一锅出', '快手', '便当友好', '宴客', or '早餐友好' unless the payload directly supports it.",
        "Return JSON only. No prose, no markdown, no code fences.",
        "Follow the provided JSON schema exactly.",
        "",
        "Candidate tags:",
    ]
    for item in tags:
        description = item["description"] or "No description"
        prompt_lines.append(f"- {item['name']}: {description}")

    prompt_lines.extend(
        [
            "",
            "Recipe payload:",
            json.dumps(compact_recipe, ensure_ascii=False),
        ]
    )

    messages = [
        {
            "role": "system",
            "content": "/no_think\nYou are a strict recipe tagging assistant. Output final valid JSON only. Never output thinking or analysis.",
        },
        {
            "role": "user",
            "content": "\n".join(prompt_lines),
        },
    ]

    try:
        raw_content = _call_ollama_chat(
            model_name,
            messages,
            response_format=TAG_JSON_SCHEMA,
        )
    except Exception as error:
        create_ai_conversation_log(
            feature="managed_tagging",
            stage="tagging",
            model=model_name,
            request_messages=messages,
            status="error",
            run_id=run_id,
            recipe_id=recipe["id"],
            error_text=str(error),
            meta={"recipe_name": recipe["name"]},
        )
        raise

    create_ai_conversation_log(
        feature="managed_tagging",
        stage="tagging",
        model=model_name,
        request_messages=messages,
        status="success",
        run_id=run_id,
        recipe_id=recipe["id"],
        response_text=raw_content,
        meta={"recipe_name": recipe["name"]},
    )

    parsed = _extract_json_payload(raw_content)
    tag_items = parsed.get("tags", [])
    if not isinstance(tag_items, list):
        return []

    allowed_names = {item["name"] for item in tags}
    selected: List[Dict[str, Any]] = []
    seen = set()
    for index, item in enumerate(tag_items):
        if isinstance(item, str):
            name = item.strip()
            confidence = max(MIN_TAG_CONFIDENCE, 0.78 - index * 0.02)
            reason = "模型直接返回标签名。"
        elif isinstance(item, dict):
            name = str((item or {}).get("name") or (item or {}).get("tag") or "").strip()
            try:
                confidence = float((item or {}).get("confidence", 0.75))
            except (TypeError, ValueError):
                confidence = 0.75
            reason = str((item or {}).get("reason") or "模型选择该标签。").strip()
        else:
            continue

        if not name or name not in allowed_names or name in seen:
            continue
        if confidence < MIN_TAG_CONFIDENCE or not reason or not _supports_tag(recipe, name):
            continue
        seen.add(name)
        selected.append(
            {
                "name": name,
                "confidence": max(0.0, min(confidence, 1.0)),
                "reason": reason,
            }
        )
    selected.sort(key=lambda value: (-value["confidence"], value["name"]))
    return selected[:MAX_TAGS_PER_RECIPE]
