import sqlite3
from contextlib import contextmanager
from typing import Generator

from app.core.config import DATA_DIR, DATABASE_PATH
from app.db.schema import SCHEMA_STATEMENTS


DEFAULT_MANAGED_TAGS = [
    {"name": "清淡", "description": "口味温和、少油少刺激，适合做保守型推荐。", "sort_order": 10},
    {"name": "浓郁", "description": "酱汁、奶油、黄油或高汤存在感强。", "sort_order": 20},
    {"name": "麻辣", "description": "辣椒、花椒、麻感或明显重辣风格。", "sort_order": 30},
    {"name": "酸辣", "description": "同时有明显酸味和辣味。", "sort_order": 40},
    {"name": "咖喱风味", "description": "以咖喱或复合香料酱为核心风味。", "sort_order": 50},
    {"name": "蒜香", "description": "蒜味是主导风味之一。", "sort_order": 60},
    {"name": "葱香", "description": "葱、葱油、红葱头等香味突出。", "sort_order": 70},
    {"name": "鲜香", "description": "鲜味突出，常见于海鲜、菌菇、高汤类。", "sort_order": 80},
    {"name": "奶香", "description": "奶油、奶酪、黄油、奶味酱汁存在感强。", "sort_order": 90},
    {"name": "酱香", "description": "酱料主导风味，例如豆瓣、沙茶、照烧等。", "sort_order": 100},
    {"name": "汤羹", "description": "以汤、羹、浓汤、暖碗形式呈现。", "sort_order": 110},
    {"name": "凉拌", "description": "冷盘、凉菜、拌菜或接近沙拉的做法。", "sort_order": 120},
    {"name": "蒸制", "description": "蒸箱、蒸锅或蒸制为关键步骤。", "sort_order": 130},
    {"name": "焖炖", "description": "焖、炖、煲、长时间收汁或慢煮。", "sort_order": 140},
    {"name": "快手", "description": "整体制作时间短，步骤相对精简。", "sort_order": 150},
    {"name": "一锅出", "description": "主料和配菜在同一锅内集中完成。", "sort_order": 160},
    {"name": "宴客", "description": "更适合待客、聚餐或正式上桌。", "sort_order": 170},
    {"name": "便当友好", "description": "适合提前准备、带饭或复热。", "sort_order": 180},
    {"name": "早餐友好", "description": "适合作为早餐或早午餐选项。", "sort_order": 190},
    {"name": "下饭", "description": "适合搭配米饭，重在配饭体验。", "sort_order": 200},
    {"name": "高蛋白", "description": "蛋白质食材占比高。", "sort_order": 210},
    {"name": "蔬菜友好", "description": "蔬菜存在感高，或整体偏蔬菜导向。", "sort_order": 220},
    {"name": "低门槛", "description": "对设备、刀工、火候要求相对低。", "sort_order": 230},
    {"name": "进阶操作", "description": "涉及较多步骤、火候控制或技术动作。", "sort_order": 240},
]


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")

        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        _run_schema_migrations(connection)
        _seed_managed_tags(connection)
        _reconcile_interrupted_ai_runs(connection)
        connection.commit()


def _run_schema_migrations(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(recipes)").fetchall()
    }
    _drop_removed_recipe_columns(connection, existing_columns)
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(recipes)").fetchall()
    }

    if "record_kind" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN record_kind TEXT NOT NULL DEFAULT 'recipe'")
    if "backlog_status" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN backlog_status TEXT")
    if "ingredients_text" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN ingredients_text TEXT")
    if "library_section" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN library_section TEXT")
    if "section_name" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN section_name TEXT")
    if "source_key" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN source_key TEXT")
    if "source_hash" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN source_hash TEXT")
    if "last_import_batch_id" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN last_import_batch_id INTEGER")
    if "sub_cuisine" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN sub_cuisine TEXT")
    if "seasonings_text" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN seasonings_text TEXT")
    if "source_reference" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN source_reference TEXT")
    if "last_reviewed_on" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN last_reviewed_on TEXT")
    if "bmd_flag" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN bmd_flag INTEGER NOT NULL DEFAULT 0")
    if "cc_flag" not in existing_columns:
        connection.execute("ALTER TABLE recipes ADD COLUMN cc_flag INTEGER NOT NULL DEFAULT 0")

    ingredient_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(ingredients)").fetchall()
    }
    if ingredient_columns and "is_visible" not in ingredient_columns:
        connection.execute("ALTER TABLE ingredients ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1")

    refine_state_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(recipe_ai_refine_state)").fetchall()
    }
    if refine_state_columns and "last_raw_response" not in refine_state_columns:
        connection.execute("ALTER TABLE recipe_ai_refine_state ADD COLUMN last_raw_response TEXT")

    refine_review_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(recipe_refine_reviews)").fetchall()
    }
    if refine_review_columns and "issue_type" not in refine_review_columns:
        connection.execute("ALTER TABLE recipe_refine_reviews ADD COLUMN issue_type TEXT")

    _migrate_recipe_pair_overrides_table(connection)

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipes_source_key
        ON recipes(source_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipes_record_kind
        ON recipes(record_kind, backlog_status)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipes_library_section
        ON recipes(library_section, section_name)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_pair_overrides_lookup
        ON recipe_pair_overrides(library_section, index_name, detail_name)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_pair_overrides_ref_lookup
        ON recipe_pair_overrides(library_section, index_ref, detail_ref)
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_recipe_pair_overrides_identity
        ON recipe_pair_overrides(
            library_section,
            COALESCE(index_ref, index_name),
            COALESCE(detail_ref, detail_name)
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_recipe_managed_tags_identity
        ON recipe_managed_tags(recipe_id, managed_tag_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_ai_tag_state_hash
        ON recipe_ai_tag_state(source_hash, model, tag_version)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_tagging_runs_status
        ON ai_tagging_runs(status, started_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_ai_refine_state_hash
        ON recipe_ai_refine_state(source_hash, model, refine_version)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_refine_runs_status
        ON ai_refine_runs(status, started_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingredients_visible
        ON ingredients(is_visible, normalized_name, name)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingredient_ai_filter_state_hash
        ON ingredient_ai_filter_state(source_hash, model, filter_version)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_ingredient_filter_runs_status
        ON ai_ingredient_filter_runs(status, started_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_refine_reviews_status
        ON recipe_refine_reviews(status, updated_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_refine_reviews_issue_type
        ON recipe_refine_reviews(issue_type, updated_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_recipe_refine_snapshots_recipe
        ON recipe_refine_snapshots(recipe_id, created_at DESC)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_conversation_logs_feature
        ON ai_conversation_logs(feature, status, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_conversation_logs_run
        ON ai_conversation_logs(run_id, recipe_id, created_at)
        """
    )


def _drop_removed_recipe_columns(connection: sqlite3.Connection, existing_columns: set[str]) -> None:
    removed_columns = {"alias", "flavor", "difficulty", "estimated_time", "servings", "tools"}
    if not removed_columns.intersection(existing_columns):
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        """
        CREATE TABLE recipes_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            record_kind TEXT NOT NULL DEFAULT 'recipe',
            backlog_status TEXT,
            source_key TEXT,
            source_hash TEXT,
            last_import_batch_id INTEGER,
            library_section TEXT,
            section_name TEXT,
            category TEXT,
            cuisine TEXT,
            sub_cuisine TEXT,
            ingredients_text TEXT,
            seasonings_text TEXT,
            steps_text TEXT,
            notes_text TEXT,
            source_reference TEXT,
            last_reviewed_on TEXT,
            bmd_flag INTEGER NOT NULL DEFAULT 0,
            cc_flag INTEGER NOT NULL DEFAULT 0,
            source_text TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (last_import_batch_id) REFERENCES import_batches(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO recipes_new (
            id,
            name,
            record_kind,
            backlog_status,
            source_key,
            source_hash,
            last_import_batch_id,
            library_section,
            section_name,
            category,
            cuisine,
            sub_cuisine,
            ingredients_text,
            seasonings_text,
            steps_text,
            notes_text,
            source_reference,
            last_reviewed_on,
            bmd_flag,
            cc_flag,
            source_text,
            created_at,
            updated_at
        )
        SELECT
            id,
            name,
            COALESCE(record_kind, 'recipe'),
            backlog_status,
            source_key,
            source_hash,
            last_import_batch_id,
            library_section,
            section_name,
            category,
            cuisine,
            sub_cuisine,
            ingredients_text,
            seasonings_text,
            steps_text,
            notes_text,
            source_reference,
            last_reviewed_on,
            COALESCE(bmd_flag, 0),
            COALESCE(cc_flag, 0),
            source_text,
            created_at,
            updated_at
        FROM recipes
        """
    )
    connection.execute("DROP TABLE recipes")
    connection.execute("ALTER TABLE recipes_new RENAME TO recipes")
    connection.execute("PRAGMA foreign_keys = ON")


def _reconcile_interrupted_ai_runs(connection: sqlite3.Connection) -> None:
    """Mark stale running background jobs as paused after backend restart.

    Web background jobs run in process threads. If the backend exits, the
    database can still contain `running` rows even though no worker thread
    exists anymore. On startup we conservatively mark those rows as paused so
    the UI can offer Resume instead of looking stuck.
    """
    interrupted_message = "后端曾在任务运行中停止；已自动标记为暂停，可继续恢复。"
    for table_name in ("ai_refine_runs", "ai_tagging_runs", "ai_ingredient_filter_runs"):
        table_exists = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        ).fetchone()
        if table_exists is None:
            continue
        connection.execute(
            f"""
            UPDATE {table_name}
            SET
                status = 'paused',
                updated_at = CURRENT_TIMESTAMP,
                error_message = CASE
                    WHEN error_message IS NULL OR TRIM(error_message) = '' THEN ?
                    ELSE error_message
                END
            WHERE status = 'running'
            """,
            (interrupted_message,),
        )


def _migrate_recipe_pair_overrides_table(connection: sqlite3.Connection) -> None:
    table_exists = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'recipe_pair_overrides'
        """
    ).fetchone()

    if table_exists is None:
        return

    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(recipe_pair_overrides)").fetchall()
    }
    expected_columns = {"id", "library_section", "index_ref", "index_name", "detail_ref", "detail_name", "created_at"}
    if existing_columns == expected_columns:
        return

    connection.execute(
        """
        CREATE TABLE recipe_pair_overrides_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_section TEXT NOT NULL,
            index_ref TEXT,
            index_name TEXT NOT NULL,
            detail_ref TEXT,
            detail_name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO recipe_pair_overrides_new (
            id,
            library_section,
            index_ref,
            index_name,
            detail_ref,
            detail_name,
            created_at
        )
        SELECT
            id,
            library_section,
            NULL AS index_ref,
            index_name,
            NULL AS detail_ref,
            detail_name,
            created_at
        FROM recipe_pair_overrides
        """
    )
    connection.execute("DROP TABLE recipe_pair_overrides")
    connection.execute("ALTER TABLE recipe_pair_overrides_new RENAME TO recipe_pair_overrides")


def _seed_managed_tags(connection: sqlite3.Connection) -> None:
    existing_count = connection.execute("SELECT COUNT(*) FROM managed_tags").fetchone()[0]
    if existing_count > 0:
        return

    for item in DEFAULT_MANAGED_TAGS:
        connection.execute(
            """
            INSERT INTO managed_tags (name, description, is_active, sort_order)
            VALUES (?, ?, 1, ?)
            """,
            (item["name"], item["description"], item["sort_order"]),
        )


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")

    try:
        yield connection
    finally:
        connection.close()
