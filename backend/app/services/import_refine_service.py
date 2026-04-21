import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional

from app.db.database import get_connection
from app.services.ai_log_service import create_ai_conversation_log
from app.services.ingredient_service import (
    sync_recipe_ingredients,
    sync_recipe_ingredients_from_items,
)
from app.services.ollama_service import (
    OLLAMA_DEFAULT_MODEL,
    _call_ollama_chat as _ollama_chat_impl,
)


REFINE_PROMPT_VERSION = "import-refine-v1"

_job_lock = threading.Lock()
_job_state = {
    "run_id": None,
    "thread": None,
    "pause_requested": False,
}


def _call_ollama_chat(
    model_name: str,
    messages: List[Dict[str, str]],
    max_attempts: int = 2,
) -> str:
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            return _ollama_chat_impl(model_name, messages)
        except Exception as error:
            last_error = error
            if "timed out" not in str(error).lower() or attempt >= max_attempts:
                raise
            time.sleep(0.5)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Ollama call failed without an error")


def get_refine_status() -> Dict[str, Any]:
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


def start_refine_run(model: Optional[str] = None) -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("A refine run is already in progress")

    model_name = (model or OLLAMA_DEFAULT_MODEL).strip()

    with get_connection() as connection:
        total_count = connection.execute(
            "SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'"
        ).fetchone()[0]
        refine_version = _build_refine_version()
        cursor = connection.execute(
            """
            INSERT INTO ai_refine_runs (
                model,
                status,
                total_count,
                refine_version,
                started_at,
                updated_at
            )
            VALUES (?, 'running', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (model_name, total_count, refine_version),
        )
        run_id = cursor.lastrowid
        connection.commit()

    thread = threading.Thread(
        target=_run_refine_job,
        args=(run_id, model_name, refine_version),
        daemon=True,
        name=f"recipe-refine-{run_id}",
    )
    with _job_lock:
        _job_state["run_id"] = run_id
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_refine_status()


def pause_refine_run() -> Dict[str, Any]:
    with _job_lock:
        if not (_job_state["thread"] and _job_state["thread"].is_alive()):
            return get_refine_status()
        _job_state["pause_requested"] = True
    return get_refine_status()


def resume_refine_run() -> Dict[str, Any]:
    with _job_lock:
        if _job_state["thread"] and _job_state["thread"].is_alive():
            raise ValueError("A refine run is already in progress")

    with get_connection() as connection:
        run = connection.execute(
            """
            SELECT id, model, refine_version, status
            FROM ai_refine_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if run is None or run["status"] != "paused":
        raise ValueError("No paused refine run available")

    thread = threading.Thread(
        target=_run_refine_job,
        args=(run["id"], run["model"], run["refine_version"]),
        daemon=True,
        name=f"recipe-refine-{run['id']}",
    )
    with _job_lock:
        _job_state["run_id"] = run["id"]
        _job_state["thread"] = thread
        _job_state["pause_requested"] = False
    thread.start()
    return get_refine_status()


def _run_refine_job(run_id: int, model_name: str, refine_version: str) -> None:
    try:
        with get_connection() as connection:
            recipes = connection.execute(
                """
                SELECT id, source_hash
                FROM recipes
                WHERE record_kind = 'recipe'
                ORDER BY id
                """
            ).fetchall()
            current_run = connection.execute(
                """
                SELECT processed_count, refined_count, skipped_count, error_count
                FROM ai_refine_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()

        processed_count = current_run["processed_count"] if current_run else 0
        refined_count = current_run["refined_count"] if current_run else 0
        skipped_count = current_run["skipped_count"] if current_run else 0
        error_count = current_run["error_count"] if current_run else 0

        for row in recipes[processed_count:]:
            with _job_lock:
                pause_requested = bool(_job_state["pause_requested"])

            if pause_requested:
                with get_connection() as connection:
                    connection.execute(
                        """
                        UPDATE ai_refine_runs
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
                with get_connection() as connection:
                    state_row = connection.execute(
                        """
                        SELECT source_hash, model, refine_version
                        FROM recipe_ai_refine_state
                        WHERE recipe_id = ?
                        """,
                        (recipe_id,),
                    ).fetchone()

                if (
                    state_row is not None
                    and state_row["source_hash"] == source_hash
                    and state_row["model"] == model_name
                    and state_row["refine_version"] == refine_version
                ):
                    skipped_count += 1
                else:
                    snapshot = _load_recipe_snapshot(recipe_id)
                    refined = _generate_refined_recipe(
                        snapshot,
                        model_name,
                        run_id=run_id,
                    )
                    with get_connection() as connection:
                        _apply_refined_recipe(connection, recipe_id, refined)
                        connection.execute(
                            """
                            INSERT INTO recipe_ai_refine_state (
                                recipe_id,
                                source_hash,
                                model,
                                refine_version,
                                refined_at,
                                last_run_id,
                                last_error
                            )
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, NULL)
                            ON CONFLICT(recipe_id) DO UPDATE SET
                                source_hash = excluded.source_hash,
                                model = excluded.model,
                                refine_version = excluded.refine_version,
                                refined_at = CURRENT_TIMESTAMP,
                                last_run_id = excluded.last_run_id,
                                last_error = NULL
                            """,
                            (recipe_id, source_hash, model_name, refine_version, run_id),
                        )
                        connection.commit()
                    refined_count += 1
            except Exception as error:
                error_count += 1
                with get_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO recipe_ai_refine_state (
                            recipe_id,
                            source_hash,
                            model,
                            refine_version,
                            refined_at,
                            last_run_id,
                            last_error
                        )
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                        ON CONFLICT(recipe_id) DO UPDATE SET
                            source_hash = excluded.source_hash,
                            model = excluded.model,
                            refine_version = excluded.refine_version,
                            refined_at = CURRENT_TIMESTAMP,
                            last_run_id = excluded.last_run_id,
                            last_error = excluded.last_error
                        """,
                        (
                            recipe_id,
                            source_hash,
                            model_name,
                            refine_version,
                            run_id,
                            str(error),
                        ),
                    )
                    connection.commit()

            processed_count += 1
            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE ai_refine_runs
                    SET
                        status = 'running',
                        processed_count = ?,
                        refined_count = ?,
                        skipped_count = ?,
                        error_count = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (processed_count, refined_count, skipped_count, error_count, run_id),
                )
                connection.commit()

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_refine_runs
                SET
                    status = 'completed',
                    processed_count = total_count,
                    refined_count = ?,
                    skipped_count = ?,
                    error_count = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (refined_count, skipped_count, error_count, run_id),
            )
            connection.commit()
    except Exception as error:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE ai_refine_runs
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
            refined_count,
            skipped_count,
            error_count,
            refine_version,
            started_at,
            updated_at,
            completed_at,
            error_message
        FROM ai_refine_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _build_refine_version() -> str:
    payload = {
        "version": REFINE_PROMPT_VERSION,
        "target_fields": [
            "ingredients_text",
            "seasonings_text",
            "steps_text",
            "notes_text",
            "ingredients",
        ],
        "rule": "preserve meaning, normalize split, do not invent unsupported facts",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
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
                source_reference,
                source_text
            FROM recipes
            WHERE id = ?
            """,
            (recipe_id,),
        ).fetchone()
        ingredient_rows = connection.execute(
            """
            SELECT
                i.name,
                ri.amount,
                ri.unit,
                ri.remark
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
        "source_text": recipe_row["source_text"] or "",
        "ingredients": [
            {
                "name": row["name"],
                "amount": row["amount"],
                "unit": row["unit"],
                "remark": row["remark"],
            }
            for row in ingredient_rows
        ],
    }


def _generate_refined_recipe(
    recipe: Dict[str, Any],
    model_name: str,
    run_id: Optional[int] = None,
) -> Dict[str, Any]:
    prompt = "\n".join(
        [
            "请根据给定菜谱信息，对已经切分出的字段做精校。",
            "目标是提高切分质量，不是改写菜谱风格。",
            "要求：",
            "1. 不要发明原文没有的信息。",
            "2. ingredients_text 只放主食材。",
            "3. seasonings_text 只放调料、酱料、香料。",
            "4. steps_text 保留做法及要点，尽量整理成清晰文本。",
            "5. notes_text 只保留备注、补充说明、替换建议等。",
            "6. ingredients 需要返回结构化食材数组。",
            "7. 如果原字段已经合理，可以保持原值。",
            "8. 只返回合法 JSON，不要 markdown，不要解释。",
            "",
            "JSON 格式：",
            "{",
            '  "ingredients_text": "主食材文本",',
            '  "seasonings_text": "调料文本",',
            '  "steps_text": "做法文本",',
            '  "notes_text": "备注文本",',
            '  "ingredients": [',
            '    {"name": "食材名", "amount": "数量", "unit": "单位", "remark": "备注"}',
            "  ]",
            "}",
            "",
            f"菜名：{recipe['name']}",
            f"专题库：{recipe['library_section']}",
            f"分组：{recipe['section_name']}",
            f"菜系：{recipe['cuisine']} / {recipe['sub_cuisine']}",
            f"当前食材：{recipe['ingredients_text']}",
            f"当前调料：{recipe['seasonings_text']}",
            f"当前做法：{recipe['steps_text']}",
            f"当前备注：{recipe['notes_text']}",
            f"来源备注：{recipe['source_reference']}",
            f"源文本：{recipe['source_text']}",
            "当前结构化食材：",
            json.dumps(recipe["ingredients"], ensure_ascii=False),
        ]
    )

    messages = [
        {"role": "system", "content": "你是菜谱字段精校器。只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_content = _call_ollama_chat(model_name, messages)
    except Exception as error:
        create_ai_conversation_log(
            feature="import_refinement",
            stage="refinement",
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
        feature="import_refinement",
        stage="refinement",
        model=model_name,
        request_messages=messages,
        status="success",
        run_id=run_id,
        recipe_id=recipe["id"],
        response_text=raw_content,
        meta={"recipe_name": recipe["name"]},
    )

    parsed = _extract_json_object(raw_content)
    ingredients = _normalize_ingredient_items(parsed.get("ingredients"))
    return {
        "ingredients_text": str(
            parsed.get("ingredients_text", "") or recipe["ingredients_text"]
        ).strip(),
        "seasonings_text": str(
            parsed.get("seasonings_text", "") or recipe["seasonings_text"]
        ).strip(),
        "steps_text": str(parsed.get("steps_text", "") or recipe["steps_text"]).strip(),
        "notes_text": str(parsed.get("notes_text", "") or recipe["notes_text"]).strip(),
        "ingredients": ingredients,
    }


def _normalize_ingredient_items(value: Any) -> List[Dict[str, Optional[str]]]:
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Optional[str]]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized.append(
            {
                "name": name,
                "amount": _normalize_optional_text(item.get("amount")),
                "unit": _normalize_optional_text(item.get("unit")),
                "remark": _normalize_optional_text(item.get("remark")),
            }
        )
    return normalized


def _normalize_optional_text(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _apply_refined_recipe(connection, recipe_id: int, refined: Dict[str, Any]) -> None:
    connection.execute(
        """
        UPDATE recipes
        SET
            ingredients_text = ?,
            seasonings_text = ?,
            steps_text = ?,
            notes_text = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            refined["ingredients_text"],
            refined["seasonings_text"],
            refined["steps_text"],
            refined["notes_text"],
            recipe_id,
        ),
    )

    if refined["ingredients"]:
        sync_recipe_ingredients_from_items(connection, recipe_id, refined["ingredients"])
    else:
        sync_recipe_ingredients(connection, recipe_id, refined["ingredients_text"])


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
