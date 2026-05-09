import hashlib
import json
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tkinter import Tk, StringVar, filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional


APP_TITLE = "Label Helper"
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_TIMEOUT_SECONDS = 240
OLLAMA_MAX_ATTEMPTS = 1
PREFERRED_MODEL = "qwen3:4b"
TAG_PROMPT_VERSION = "managed-tag-v5-no-think-compact"
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


class RecipeDbTaggerApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("460x290")
        self.root.resizable(False, False)

        self.db_path: Optional[Path] = None
        self.progress_var = StringVar(value="0 / 0")
        self.status_var = StringVar(value="Open a database to start.")
        self.summary_var = StringVar(value="Total 0 | Success 0 | Failed 0 | Pending 0")
        self.model_var = StringVar(value="")
        self.available_models: List[str] = []

        self.worker_thread: Optional[threading.Thread] = None
        self.pause_requested = False
        self.last_notified_signature: Optional[str] = None

        self._build_ui()
        self._load_models()
        self._refresh_buttons()
        self.root.after(500, self._poll_status)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        model_row = ttk.Frame(frame)
        model_row.pack(fill="x", pady=(0, 12))
        ttk.Label(model_row, text="模型").pack(side="left", padx=(0, 8))
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model_var, state="readonly")
        self.model_combo.pack(side="left", fill="x", expand=True)
        self.model_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_model_changed())

        progress = ttk.Label(
            frame,
            textvariable=self.progress_var,
            anchor="center",
            font=("Segoe UI", 28, "bold"),
        )
        progress.pack(fill="x", expand=True, pady=(8, 16))

        status = ttk.Label(
            frame,
            textvariable=self.status_var,
            anchor="center",
            wraplength=360,
        )
        status.pack(fill="x", pady=(0, 12))

        summary = ttk.Label(frame, textvariable=self.summary_var, anchor="center")
        summary.pack(fill="x", pady=(0, 12))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        self.open_button = ttk.Button(buttons, text="打开数据库", command=self.open_database)
        self.open_button.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.start_button = ttk.Button(buttons, text="开始", command=self.start_run)
        self.start_button.pack(side="left", expand=True, fill="x", padx=6)

        self.pause_button = ttk.Button(buttons, text="暂停", command=self.pause_run)
        self.pause_button.pack(side="left", expand=True, fill="x", padx=6)

        self.resume_button = ttk.Button(buttons, text="继续", command=self.resume_run)
        self.resume_button.pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _load_models(self) -> None:
        self.available_models = fetch_ollama_models()
        self.model_combo["values"] = self.available_models
        if not self.available_models:
            self.model_var.set("")
            return
        current_model = self.model_var.get().strip()
        if current_model in self.available_models:
            return
        default_model = PREFERRED_MODEL if PREFERRED_MODEL in self.available_models else self.available_models[0]
        self.model_var.set(default_model)

    def _selected_model(self) -> str:
        return self.model_var.get().strip()

    def _on_model_changed(self) -> None:
        self.last_notified_signature = None
        if self.db_path is not None:
            reconcile_interrupted_runs(self.db_path, self._selected_model())
            self._load_progress_from_database()
        self._refresh_buttons()

    def open_database(self) -> None:
        path = filedialog.askopenfilename(
            title="选择数据库文件",
            filetypes=[
                ("SQLite Database", "*.db *.sqlite *.sqlite3"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return

        try:
            self._load_models()
            if not self.available_models:
                raise RuntimeError("No Ollama model available")
            self.db_path = Path(path)
            ensure_schema(self.db_path)
            reconcile_interrupted_runs(self.db_path, self._selected_model())
            self._load_progress_from_database()
            self.root.title(f"{APP_TITLE} - {self.db_path.name}")
        except Exception as error:
            self.db_path = None
            self.progress_var.set("0 / 0")
            self.status_var.set("Open failed.")
            messagebox.showerror("打开失败", str(error))

        self._refresh_buttons()

    def start_run(self) -> None:
        if self.db_path is None or (self.worker_thread and self.worker_thread.is_alive()):
            return
        model = self._selected_model()
        if not model:
            messagebox.showerror("无法开始", "No Ollama model available")
            return

        run_id = create_tagging_run(self.db_path, model, build_tag_version(self.db_path))
        self.pause_requested = False
        self.worker_thread = threading.Thread(
            target=run_tagging_job,
            args=(self.db_path, run_id, model, build_tag_version(self.db_path), self._pause_flag_getter),
            daemon=True,
            name=f"db-tag-{run_id}",
        )
        self.worker_thread.start()
        self._refresh_buttons()

    def pause_run(self) -> None:
        self.pause_requested = True
        self._refresh_buttons()

    def resume_run(self) -> None:
        if self.db_path is None or (self.worker_thread and self.worker_thread.is_alive()):
            return
        model = self._selected_model()
        if not model:
            messagebox.showerror("无法继续", "No Ollama model available")
            return

        paused_run = load_latest_run(self.db_path, model=model, statuses=("paused",))
        if paused_run is None:
            messagebox.showinfo("继续", "当前模型没有可继续的暂停任务。")
            return

        self.pause_requested = False
        self.worker_thread = threading.Thread(
            target=run_tagging_job,
            args=(self.db_path, paused_run["id"], model, paused_run["tag_version"], self._pause_flag_getter),
            daemon=True,
            name=f"db-tag-{paused_run['id']}",
        )
        self.worker_thread.start()
        self._refresh_buttons()

    def _pause_flag_getter(self) -> bool:
        return self.pause_requested

    def _poll_status(self) -> None:
        try:
            if self.db_path is not None:
                self._load_progress_from_database()
        finally:
            self.root.after(500, self._poll_status)

    def _load_progress_from_database(self) -> None:
        if self.db_path is None:
            self.progress_var.set("0 / 0")
            self.status_var.set("Open a database to start.")
            self.summary_var.set("Total 0 | Success 0 | Failed 0 | Pending 0")
            return

        model = self._selected_model()
        tag_version = build_tag_version(self.db_path)
        summary = load_tagging_summary(self.db_path, model, tag_version)
        self.summary_var.set(
            f"Total {summary['total']} | Success {summary['success']} | Failed {summary['failed']} | Pending {summary['pending']}"
        )
        run = load_latest_run(self.db_path, model=model)
        total_count = get_total_recipe_count(self.db_path)

        if run is None:
            self.progress_var.set(f"0 / {total_count}")
            self.status_var.set("Ready.")
            self._refresh_buttons()
            return

        self.progress_var.set(f"{run['processed_count']} / {run['total_count']}")
        self.status_var.set(format_run_status(run))
        self._refresh_buttons(status=run["status"])

        is_worker_alive = bool(self.worker_thread and self.worker_thread.is_alive())
        if not is_worker_alive and run["status"] in {"completed", "failed", "paused"}:
            signature = json.dumps(
                {
                    "run_id": run["id"],
                    "status": run["status"],
                    "processed": run["processed_count"],
                    "tagged": run["tagged_count"],
                    "skipped": run["skipped_count"],
                    "errors": run["error_count"],
                    "model": run["model"],
                },
                sort_keys=True,
            )
            if signature != self.last_notified_signature:
                self.last_notified_signature = signature
                first_error = load_first_error(self.db_path, run["id"], model)
                self._show_completion_message(run, first_error)

    def _show_completion_message(self, run: Dict[str, Any], first_error: Optional[str]) -> None:
        message_lines = [
            f"进度: {run['processed_count']} / {run['total_count']}",
            f"成功: {run['tagged_count']}",
            f"跳过: {run['skipped_count']}",
            f"错误: {run['error_count']}",
        ]
        if first_error:
            message_lines.extend(["", f"首条错误: {first_error}"])

        if run["status"] == "completed":
            messagebox.showinfo("打标签完成", "\n".join(message_lines))
        elif run["status"] == "paused":
            messagebox.showinfo("打标签已暂停", "\n".join(message_lines))
        else:
            if run.get("error_message"):
                message_lines.extend(["", f"任务错误: {run['error_message']}"])
            messagebox.showerror("打标签失败", "\n".join(message_lines))

    def _refresh_buttons(self, status: Optional[str] = None) -> None:
        has_db = self.db_path is not None
        model_available = bool(self._selected_model())
        running = bool(self.worker_thread and self.worker_thread.is_alive())
        latest_run = load_latest_run(self.db_path, model=self._selected_model()) if has_db and model_available else None
        latest_status = status or (latest_run["status"] if latest_run else None)

        self.open_button.configure(state="normal" if not running else "disabled")
        self.model_combo.configure(state="readonly" if not running else "disabled")
        self.start_button.configure(state="normal" if has_db and model_available and not running else "disabled")
        self.pause_button.configure(state="normal" if running else "disabled")
        self.resume_button.configure(
            state="normal" if has_db and model_available and not running and latest_status == "paused" else "disabled"
        )


def fetch_ollama_models() -> List[str]:
    request = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))
    names = [item.get("name", "").strip() for item in payload.get("models", []) if item.get("name")]
    return names


def call_ollama_chat(
    model_name: str,
    messages: List[Dict[str, str]],
    *,
    response_format: Optional[Any] = None,
    max_attempts: int = OLLAMA_MAX_ATTEMPTS,
) -> str:
    last_error: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            payload: Dict[str, Any] = {
                "model": model_name,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "thinking": False,
                    "num_ctx": 2048,
                    "num_predict": 1536,
                },
                "messages": messages,
            }
            if response_format is not None:
                payload["format"] = response_format

            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                OLLAMA_CHAT_URL,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            message = payload.get("message") or {}
            content = str(message.get("content") or "").strip()
            thinking = str(message.get("thinking") or "").strip()
            if thinking and not content:
                content = thinking
            if not content:
                raise RuntimeError("Ollama returned an empty response")
            return content
        except urllib.error.HTTPError as error:
            try:
                detail = error.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(error)
            last_error = RuntimeError(f"Ollama HTTP {error.code}: {detail}")
        except Exception as error:
            last_error = error

        if last_error is None:
            continue
        if "timed out" not in str(last_error).lower() or attempt >= max_attempts:
            raise last_error

    if last_error is not None:
        raise last_error
    raise RuntimeError("Ollama call failed without an error")


def ensure_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS managed_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_managed_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                managed_tag_id INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'ai',
                confidence REAL,
                reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_ai_tag_state (
                recipe_id INTEGER PRIMARY KEY,
                source_hash TEXT,
                model TEXT,
                tag_version TEXT,
                tagged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_run_id INTEGER,
                last_error TEXT
            )
            """
        )
        connection.execute(
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
            )
            """
        )
        run_columns = {row["name"] for row in connection.execute("PRAGMA table_info(ai_tagging_runs)").fetchall()}
        if "current_recipe_id" not in run_columns:
            connection.execute("ALTER TABLE ai_tagging_runs ADD COLUMN current_recipe_id INTEGER")
        if "current_recipe_name" not in run_columns:
            connection.execute("ALTER TABLE ai_tagging_runs ADD COLUMN current_recipe_name TEXT")
        if "current_recipe_started_at" not in run_columns:
            connection.execute("ALTER TABLE ai_tagging_runs ADD COLUMN current_recipe_started_at TEXT")
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
        seed_managed_tags(connection)
        connection.commit()


def seed_managed_tags(connection: sqlite3.Connection) -> None:
    existing_count = connection.execute("SELECT COUNT(*) FROM managed_tags").fetchone()[0]
    if existing_count:
        return
    for item in DEFAULT_MANAGED_TAGS:
        connection.execute(
            """
            INSERT INTO managed_tags (name, description, is_active, sort_order)
            VALUES (?, ?, 1, ?)
            """,
            (item["name"], item["description"], item["sort_order"]),
        )


def build_tag_version(db_path: Path) -> str:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
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


def get_total_recipe_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'"
        ).fetchone()[0]


def should_skip_recipe_tagging(
    db_path: Path,
    recipe_id: int,
    source_hash: str,
    model_name: str,
    tag_version: str,
) -> bool:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
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


def load_tagging_summary(db_path: Path, model_name: str, tag_version: str) -> Dict[str, int]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        recipes = connection.execute(
            """
            SELECT id, source_hash
            FROM recipes
            WHERE record_kind = 'recipe'
            ORDER BY id
            """
        ).fetchall()
        state_rows = connection.execute(
            """
            SELECT recipe_id, source_hash, model, tag_version, last_error
            FROM recipe_ai_tag_state
            WHERE model = ?
            """,
            (model_name,),
        ).fetchall()

    state_by_recipe = {int(row["recipe_id"]): row for row in state_rows}
    success = 0
    failed = 0
    pending = 0
    for recipe in recipes:
        state = state_by_recipe.get(int(recipe["id"]))
        if state is None:
            pending += 1
            continue
        if (
            (state["source_hash"] or "") != (recipe["source_hash"] or "")
            or state["model"] != model_name
            or state["tag_version"] != tag_version
        ):
            pending += 1
            continue
        if (state["last_error"] or "").strip():
            failed += 1
            pending += 1
        else:
            success += 1

    return {
        "total": len(recipes),
        "success": success,
        "failed": failed,
        "pending": pending,
    }


def reconcile_interrupted_runs(db_path: Path, model_name: str) -> None:
    if not model_name:
        return
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ai_tagging_runs
            SET status = 'paused',
                current_recipe_id = NULL,
                current_recipe_name = NULL,
                current_recipe_started_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE model = ? AND status = 'running'
            """,
            (model_name,),
        )
        connection.commit()


def load_latest_run(db_path: Optional[Path], model: str = "", statuses: tuple[str, ...] = ()) -> Optional[Dict[str, Any]]:
    if db_path is None:
        return None
    sql = """
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
                error_message,
                current_recipe_id,
                current_recipe_name,
                current_recipe_started_at
        FROM ai_tagging_runs
    """
    clauses: List[str] = []
    params: List[Any] = []
    if model:
        clauses.append("model = ?")
        params.append(model)
    if statuses:
        placeholders = ", ".join("?" for _ in statuses)
        clauses.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id DESC LIMIT 1"

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(sql, params).fetchone()
    return dict(row) if row else None


def format_run_status(run: Dict[str, Any]) -> str:
    status = str(run.get("status") or "")
    if status == "running":
        recipe_id = run.get("current_recipe_id")
        recipe_name = str(run.get("current_recipe_name") or "").strip()
        elapsed = format_elapsed_seconds(str(run.get("current_recipe_started_at") or ""))
        label = f"#{recipe_id} {recipe_name}".strip() if recipe_id else "current recipe"
        if elapsed:
            return f"Processing: {label} ({elapsed})"
        return f"Processing: {label}"
    if status == "paused":
        return "Paused. Click resume to continue."
    if status == "completed":
        return "Completed."
    if status == "failed":
        return "Failed. Check the error dialog."
    return "Ready."


def format_elapsed_seconds(started_at: str) -> str:
    if not started_at:
        return ""
    try:
        parsed = datetime.strptime(started_at.split(".")[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    except ValueError:
        return ""
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


def load_first_error(db_path: Path, run_id: int, model_name: str) -> Optional[str]:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT last_error
            FROM recipe_ai_tag_state
            WHERE model = ? AND last_run_id = ? AND last_error IS NOT NULL
            ORDER BY recipe_id
            LIMIT 1
            """,
            (model_name, run_id),
        ).fetchone()
    return row[0] if row else None


def create_tagging_run(db_path: Path, model_name: str, tag_version: str) -> int:
    with sqlite3.connect(db_path) as connection:
        total_count = connection.execute(
            "SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'"
        ).fetchone()[0]
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
        connection.commit()
        return int(cursor.lastrowid)


def set_run_current_recipe(db_path: Path, run_id: int, recipe_id: Optional[int], recipe_name: Optional[str]) -> None:
    with sqlite3.connect(db_path) as connection:
        if recipe_id is None:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET current_recipe_id = NULL,
                    current_recipe_name = NULL,
                    current_recipe_started_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (run_id,),
            )
        else:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET current_recipe_id = ?,
                    current_recipe_name = ?,
                    current_recipe_started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (recipe_id, recipe_name or "", run_id),
            )
        connection.commit()


def reset_tagging_run_for_pending_work(
    db_path: Path,
    run_id: int,
    *,
    total_count: int,
    processed_count: int,
    tagged_count: int,
    skipped_count: int,
    error_count: int,
) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ai_tagging_runs
            SET status = 'running',
                total_count = ?,
                processed_count = ?,
                tagged_count = ?,
                skipped_count = ?,
                error_count = ?,
                current_recipe_id = NULL,
                current_recipe_name = NULL,
                current_recipe_started_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (total_count, processed_count, tagged_count, skipped_count, error_count, run_id),
        )
        connection.commit()


def load_active_tags(db_path: Path) -> List[Dict[str, Any]]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, name, description, sort_order
            FROM managed_tags
            WHERE is_active = 1
            ORDER BY sort_order, id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_recipe_snapshot(db_path: Path, recipe_id: int) -> Dict[str, Any]:
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
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
                notes_text
            FROM recipes
            WHERE id = ?
            """,
            (recipe_id,),
        ).fetchone()
        ingredient_rows = connection.execute(
            """
            SELECT COALESCE(i.normalized_name, i.name) AS ingredient_name
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
        "notes_text": recipe_row["notes_text"] or "",
        "ingredients": [row["ingredient_name"] for row in ingredient_rows],
    }


def extract_json_payload(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()
    cleaned = strip_thinking_process(cleaned)
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


def strip_thinking_process(text: str) -> str:
    markers = [
        "Final JSON:",
        "Final Answer:",
        "Output:",
        "Result:",
        "JSON:",
    ]
    lowered = text.lower()
    if "thinking process" not in lowered and "analysis" not in lowered:
        return text
    for marker in markers:
        index = text.rfind(marker)
        if index >= 0:
            return text[index + len(marker) :].strip()
    last_object = text.rfind('{"tags"')
    if last_object >= 0:
        return text[last_object:].strip()
    return text


def supports_tag(recipe: Dict[str, Any], tag_name: str) -> bool:
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


def generate_tags_for_recipe(recipe: Dict[str, Any], tags: List[Dict[str, Any]], model_name: str) -> List[Dict[str, Any]]:
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

    raw_content = call_ollama_chat(
        model_name,
        messages,
        response_format=TAG_JSON_SCHEMA,
    )
    parsed = extract_json_payload(raw_content)
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
        try:
            confidence = float((item or {}).get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = str((item or {}).get("reason", "")).strip()
        if confidence < MIN_TAG_CONFIDENCE or not reason or not supports_tag(recipe, name):
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


def has_source_for_tagging(recipe: Dict[str, Any]) -> bool:
    text = " ".join(
        str(recipe.get(key) or "").strip()
        for key in ("name", "ingredients_text", "seasonings_text", "notes_text")
    ).strip()
    return bool(text or recipe.get("ingredients"))


def normalize_selected_tags(recipe: Dict[str, Any], tag_items: object, tags: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(tag_items, list):
        return []

    allowed_names = {item["name"] for item in tags}
    selected: List[Dict[str, Any]] = []
    seen = set()
    for item in tag_items:
        name = str((item or {}).get("name", "")).strip()
        if not name or name not in allowed_names or name in seen:
            continue
        try:
            confidence = float((item or {}).get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        reason = str((item or {}).get("reason", "")).strip()
        if confidence < MIN_TAG_CONFIDENCE or not reason or not supports_tag(recipe, name):
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


def replace_recipe_managed_tags(connection: sqlite3.Connection, recipe_id: int, selected_tags: List[Dict[str, Any]]) -> None:
    connection.execute("DELETE FROM recipe_managed_tags WHERE recipe_id = ?", (recipe_id,))
    if not selected_tags:
        return

    connection.row_factory = sqlite3.Row
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


def run_tagging_job(
    db_path: Path,
    run_id: int,
    model_name: str,
    tag_version: str,
    pause_getter: Callable[[], bool],
) -> None:
    try:
        active_tags = load_active_tags(db_path)
        if not active_tags:
            raise RuntimeError("No active managed tags found in database")

        with sqlite3.connect(db_path) as connection:
            connection.row_factory = sqlite3.Row
            recipes = connection.execute(
                """
                SELECT id, name, source_hash
                FROM recipes
                WHERE record_kind = 'recipe'
                ORDER BY id
                """
            ).fetchall()

        pending_recipes: List[sqlite3.Row] = []
        skipped_count = 0
        for recipe_row in recipes:
            recipe_id = int(recipe_row["id"])
            source_hash = recipe_row["source_hash"] or ""
            if should_skip_recipe_tagging(db_path, recipe_id, source_hash, model_name, tag_version):
                skipped_count += 1
            else:
                pending_recipes.append(recipe_row)

        processed_count = 0
        tagged_count = 0
        error_count = 0
        reset_tagging_run_for_pending_work(
            db_path,
            run_id,
            total_count=len(pending_recipes),
            processed_count=processed_count,
            tagged_count=tagged_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )

        for row in pending_recipes:
            if pause_getter():
                with sqlite3.connect(db_path) as connection:
                    connection.execute(
                        """
                        UPDATE ai_tagging_runs
                        SET status = 'paused',
                            current_recipe_id = NULL,
                            current_recipe_name = NULL,
                            current_recipe_started_at = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (run_id,),
                    )
                    connection.commit()
                return

            recipe_id = row["id"]
            recipe_name = str(row["name"] or "").strip()
            source_hash = row["source_hash"]
            set_run_current_recipe(db_path, run_id, recipe_id, recipe_name)
            try:
                if should_skip_recipe_tagging(db_path, recipe_id, source_hash or "", model_name, tag_version):
                    skipped_count += 1
                else:
                    snapshot = load_recipe_snapshot(db_path, recipe_id)
                    snapshot["source_hash"] = source_hash
                    if not has_source_for_tagging(snapshot):
                        result = []
                    else:
                        result = generate_tags_for_recipe(snapshot, active_tags, model_name)
                    with sqlite3.connect(db_path) as connection:
                        replace_recipe_managed_tags(connection, recipe_id, result)
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
                processed_count += 1
                with sqlite3.connect(db_path) as connection:
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
            except Exception as error:
                error_count += 1
                with sqlite3.connect(db_path) as connection:
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
                with sqlite3.connect(db_path) as connection:
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

        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET
                    status = 'completed',
                    processed_count = total_count,
                    tagged_count = ?,
                    skipped_count = ?,
                    error_count = ?,
                    current_recipe_id = NULL,
                    current_recipe_name = NULL,
                    current_recipe_started_at = NULL,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (tagged_count, skipped_count, error_count, run_id),
            )
            connection.commit()
    except Exception as error:
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """
                UPDATE ai_tagging_runs
                SET
                    status = 'failed',
                    current_recipe_id = NULL,
                    current_recipe_name = NULL,
                    current_recipe_started_at = NULL,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = ?
                WHERE id = ?
                """,
                (str(error), run_id),
            )
            connection.commit()


def main() -> None:
    root = Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    app = RecipeDbTaggerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
