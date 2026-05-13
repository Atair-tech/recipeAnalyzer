SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS recipes (
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
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        normalized_name TEXT NOT NULL,
        is_visible INTEGER NOT NULL DEFAULT 1
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ingredient_aliases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ingredient_id INTEGER NOT NULL,
        alias_name TEXT NOT NULL,
        source TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        ingredient_id INTEGER NOT NULL,
        amount TEXT,
        unit TEXT,
        remark TEXT,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        type TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        raw_meta TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_import_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL,
        row_index INTEGER NOT NULL,
        raw_json TEXT NOT NULL,
        parse_status TEXT NOT NULL DEFAULT 'pending',
        parse_result_json TEXT,
        FOREIGN KEY (batch_id) REFERENCES import_batches(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_pair_overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        library_section TEXT NOT NULL,
        index_ref TEXT,
        index_name TEXT NOT NULL,
        detail_ref TEXT,
        detail_name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS managed_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_managed_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        managed_tag_id INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'ai',
        confidence REAL,
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (managed_tag_id) REFERENCES managed_tags(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_ai_tag_state (
        recipe_id INTEGER PRIMARY KEY,
        source_hash TEXT,
        model TEXT,
        tag_version TEXT,
        tagged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_run_id INTEGER,
        last_error TEXT,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (last_run_id) REFERENCES ai_tagging_runs(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_tagging_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        total_count INTEGER NOT NULL DEFAULT 0,
        processed_count INTEGER NOT NULL DEFAULT 0,
        tagged_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        tag_version TEXT,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        error_message TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_ai_refine_state (
        recipe_id INTEGER PRIMARY KEY,
        source_hash TEXT,
        model TEXT,
        refine_version TEXT,
        refined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_run_id INTEGER,
        last_error TEXT,
        last_raw_response TEXT,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_refine_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        total_count INTEGER NOT NULL DEFAULT 0,
        processed_count INTEGER NOT NULL DEFAULT 0,
        refined_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        refine_version TEXT,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        error_message TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ingredient_ai_filter_state (
        ingredient_id INTEGER PRIMARY KEY,
        source_hash TEXT,
        model TEXT,
        filter_version TEXT,
        filtered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_run_id INTEGER,
        is_visible INTEGER NOT NULL DEFAULT 1,
        reason TEXT,
        last_error TEXT,
        last_raw_response TEXT,
        FOREIGN KEY (ingredient_id) REFERENCES ingredients(id) ON DELETE CASCADE,
        FOREIGN KEY (last_run_id) REFERENCES ai_ingredient_filter_runs(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_ingredient_filter_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        total_count INTEGER NOT NULL DEFAULT 0,
        processed_count INTEGER NOT NULL DEFAULT 0,
        kept_count INTEGER NOT NULL DEFAULT 0,
        hidden_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        filter_version TEXT,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        error_message TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_refine_reviews (
        recipe_id INTEGER PRIMARY KEY,
        status TEXT NOT NULL,
        issue_type TEXT,
        note TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS recipe_refine_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipe_id INTEGER NOT NULL,
        run_id INTEGER,
        model TEXT,
        refine_version TEXT,
        before_ingredients_json TEXT NOT NULL,
        after_ingredients_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE CASCADE,
        FOREIGN KEY (run_id) REFERENCES ai_refine_runs(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_conversation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        feature TEXT NOT NULL,
        stage TEXT,
        model TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'success',
        run_id INTEGER,
        recipe_id INTEGER,
        request_messages_json TEXT NOT NULL,
        response_text TEXT,
        error_text TEXT,
        meta_json TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recipe_id) REFERENCES recipes(id) ON DELETE SET NULL
    );
    """,
]
