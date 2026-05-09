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
from typing import Callable, List, Optional, Tuple


APP_TITLE = "Data Helper"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
OLLAMA_TIMEOUT_SECONDS = 240
OLLAMA_MAX_ATTEMPTS = 1
REFINE_PROMPT_VERSION = "import-refine-v8-raw-text-only-fallback"
PREFERRED_MODEL = "qwen3:4b"

INGREDIENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "amount": {"type": "string"},
                    "unit": {"type": "string"},
                    "remark": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ingredients"],
    "additionalProperties": False,
}

OPTIONAL_PREFIXES = ("可加", "可放", "可用", "也可用", "也可加", "建议加", "最后加")
OPTIONAL_SUFFIXES = ("可加", "可放", "可用", "也可用", "更好吃", "提味", "增香")
DROP_HINTS = (
    "%",
    "/",
    "\\",
    "*",
    "+",
    "=",
    "正常来说",
    "经典",
    "低卡",
    "口味",
    "含水量",
    "左右",
    "以上",
    "建议",
    "推荐",
    "如果",
    "或者",
    "然后",
    "需要",
    "常用食材",
    "原版",
    "见牛肉词条",
    "见猪肉词条",
    "见鸡肉词条",
    "词条",
    "ingredient",
    "anotheringredient",
    "yetanotheringredient",
)
BRAND_PREFIXES = (
    "六必居",
    "暴肌独角兽",
    "薄荷记",
    "顶丰",
    "李锦记",
    "盒马",
    "牛头牌",
    "都乐",
    "和润",
    "欧萨",
    "单山",
    "广合",
    "圃美多",
)
GENERIC_PREFIXES = ("点缀用的", "搭配用的", "佐餐用的", "原版用的", "可选搭配", "搭配蔬菜")
INGREDIENT_SEGMENTS = (
    "葡萄叶",
    "鸡胸肉",
    "鸡腿肉",
    "整鸡",
    "鸡腿",
    "鸡翅",
    "鸡块",
    "薄荷",
    "欧芹",
    "莳萝",
    "海带",
    "裙带菜",
    "南瓜",
    "土豆",
    "红薯",
    "茄子",
    "豆角",
    "彩椒",
    "尖椒",
    "麻椒",
    "雪菜",
    "青菜",
)
AMOUNT_IN_NAME_PATTERN = re.compile(
    r"(?P<prefix>.*?)(?P<amount>\d+(?:\.\d+)?(?:[-~～至到]\d+(?:\.\d+)?)?)(?P<unit>g|kg|ml|mL|L|l|克|千克|毫升|公升|个|只|颗|粒|瓣|根|片|条|朵|盒|包|袋|勺|tsp|tbsp|cup)$",
    re.I,
)
AMOUNT_WITH_UNIT_PATTERN = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?(?:[-~～至到]\d+(?:\.\d+)?)?)(?P<unit>g|kg|ml|mL|L|l|克|千克|毫升|公升|个|只|颗|粒|瓣|根|片|条|朵|盒|包|袋|勺|tsp|tbsp|cup)$",
    re.I,
)
PACKAGE_HINT_PATTERN = re.compile(r"(半包|半袋|一包|一袋|半盒|一盒)$")
FALLBACK_SPLIT_PATTERN = re.compile(r"[，,、；;]")
FALLBACK_CHOICE_PATTERN = re.compile(r"(?:/|／|\\|or|OR|或)")
TRAILING_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.*?)(?P<amount>\d+(?:\.\d+)?(?:[-~～至到]\d+(?:\.\d+)?)?)(?P<unit>g|kg|ml|mL|L|l|克|千克|毫升|公升|个|只|颗|粒|瓣|根|片|条|朵|枚|罐|盒|包|袋|勺|tsp|tbsp|cup)(?:约|左右|记)?$",
    re.I,
)
INGREDIENT_ALIASES = {
    "包浆豆腐": "豆腐",
    "中豆腐": "豆腐",
    "嫩豆腐": "豆腐",
    "老豆腐": "豆腐",
    "内酯豆腐": "豆腐",
    "可生食鸡蛋": "鸡蛋",
    "蛋液": "鸡蛋",
    "鸡蛋液": "鸡蛋",
    "小番茄": "番茄",
    "西红柿": "番茄",
    "圣女果": "番茄",
    "马铃薯": "土豆",
    "洋芋": "土豆",
}


class RecipeDbRefinerApp:
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

        summary = ttk.Label(
            frame,
            textvariable=self.summary_var,
            anchor="center",
            wraplength=380,
        )
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

    def _on_model_changed(self) -> None:
        self.last_notified_signature = None
        if self.db_path is not None:
            reconcile_interrupted_runs(self.db_path, self._selected_model())
            self._load_progress_from_database()
        self._refresh_buttons()

    def _selected_model(self) -> str:
        return self.model_var.get().strip()

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
            self.summary_var.set("Total 0 | Success 0 | Failed 0 | Pending 0")
            messagebox.showerror("打开失败", str(error))

        self._refresh_buttons()

    def start_run(self) -> None:
        if self.db_path is None or (self.worker_thread and self.worker_thread.is_alive()):
            return
        model = self._selected_model()
        if not model:
            messagebox.showerror("无法开始", "No Ollama model available")
            return

        paused_run = load_latest_paused_run(self.db_path, model)
        if paused_run is not None:
            self.resume_run()
            return

        run_id = create_refine_run(self.db_path, model, build_refine_version(model))
        self.pause_requested = False
        self.worker_thread = threading.Thread(
            target=run_refine_job,
            args=(self.db_path, run_id, model, build_refine_version(model), self._pause_flag_getter),
            daemon=True,
            name=f"db-refine-{run_id}",
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
            return

        paused_run = load_latest_paused_run(self.db_path, model)
        if paused_run is None:
            return

        self.pause_requested = False
        self.worker_thread = threading.Thread(
            target=run_refine_job,
            args=(self.db_path, paused_run["id"], model, paused_run["refine_version"], self._pause_flag_getter),
            daemon=True,
            name=f"db-refine-{paused_run['id']}",
        )
        self.worker_thread.start()
        self._refresh_buttons()

    def _pause_flag_getter(self) -> bool:
        return self.pause_requested

    def _poll_status(self) -> None:
        latest_status = None
        if self.db_path is not None:
            try:
                self._load_progress_from_database()
                latest_status = load_latest_run_status(self.db_path, self._selected_model())
            except Exception:
                pass

        if self.worker_thread and not self.worker_thread.is_alive():
            self.worker_thread = None
            self.pause_requested = False

        self._maybe_notify_run_result(latest_status)
        self._refresh_buttons()
        self.root.after(700, self._poll_status)

    def _load_progress_from_database(self) -> None:
        status = load_latest_run_status(self.db_path, self._selected_model()) if self.db_path else None
        self._load_summary_from_database()
        if not status:
            total = count_target_recipes(self.db_path) if self.db_path else 0
            self.progress_var.set(f"0 / {total}")
            self.status_var.set("Ready.")
            return
        self.progress_var.set(f"{status['processed_count']} / {status['total_count']}")
        self.status_var.set(format_run_status(status))

    def _load_summary_from_database(self) -> None:
        if self.db_path is None:
            self.summary_var.set("Total 0 | Success 0 | Failed 0 | Pending 0")
            return
        model = self._selected_model()
        if not model:
            self.summary_var.set("Total 0 | Success 0 | Failed 0 | Pending 0")
            return
        try:
            summary = load_refine_summary(self.db_path, model, build_refine_version(model))
        except Exception:
            return
        self.summary_var.set(
            f"Total {summary['total']} | Success {summary['success']} | Failed {summary['failed']} | Pending {summary['pending']}"
        )

    def _maybe_notify_run_result(self, status: Optional[sqlite3.Row]) -> None:
        if status is None:
            return
        if status["status"] not in {"completed", "failed", "paused"}:
            return

        signature = "|".join(
            [
                str(status["id"]),
                str(status["status"]),
                str(status["processed_count"]),
                str(status["refined_count"]),
                str(status["skipped_count"]),
                str(status["error_count"]),
                str(status["updated_at"]),
            ]
        )
        if signature == self.last_notified_signature:
            return

        self.last_notified_signature = signature

        title_map = {
            "completed": "精校完成",
            "paused": "精校已暂停",
            "failed": "精校失败",
        }
        lines = [
            f"进度：{status['processed_count']} / {status['total_count']}",
            f"成功：{status['refined_count']}",
            f"跳过：{status['skipped_count']}",
            f"错误：{status['error_count']}",
        ]
        first_error = load_first_error_message(self.db_path, self._selected_model()) if self.db_path else None
        first_raw_response = load_first_error_raw_response(self.db_path, self._selected_model()) if self.db_path else None
        if first_error:
            lines.append("")
            lines.append(f"首条错误：{first_error}")
        if first_raw_response:
            preview = first_raw_response.strip().replace("\r", " ").replace("\n", " ")
            if len(preview) > 240:
                preview = preview[:240] + "..."
            lines.append("")
            lines.append(f"首条原始响应：{preview}")
        elif status["error_message"]:
            lines.append("")
            lines.append(f"错误信息：{status['error_message']}")
        messagebox.showinfo(title_map.get(status["status"], "任务结果"), "\n".join(lines))

    def _refresh_buttons(self) -> None:
        db_ready = self.db_path is not None
        running = bool(self.worker_thread and self.worker_thread.is_alive())
        paused_run = load_latest_paused_run(self.db_path, self._selected_model()) if db_ready and not running else None

        self.open_button.configure(state="normal" if not running else "disabled")
        self.model_combo.configure(state="readonly" if not running and self.available_models else "disabled")
        self.start_button.configure(state="normal" if db_ready and not running and self._selected_model() else "disabled")
        self.pause_button.configure(state="normal" if running else "disabled")
        self.resume_button.configure(state="normal" if paused_run and not running else "disabled")


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_schema(db_path: Path) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_ai_refine_state (
                recipe_id INTEGER PRIMARY KEY,
                source_hash TEXT,
                model TEXT,
                refine_version TEXT,
                refined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_run_id INTEGER,
                last_error TEXT,
                last_raw_response TEXT
            )
            """
        )
        connection.execute(
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
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_refine_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL,
                run_id INTEGER,
                model TEXT NOT NULL,
                refine_version TEXT NOT NULL,
                before_ingredients_json TEXT NOT NULL,
                after_ingredients_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(recipe_ai_refine_state)").fetchall()}
        if "last_raw_response" not in columns:
            connection.execute("ALTER TABLE recipe_ai_refine_state ADD COLUMN last_raw_response TEXT")
        run_columns = {row["name"] for row in connection.execute("PRAGMA table_info(ai_refine_runs)").fetchall()}
        if "current_recipe_id" not in run_columns:
            connection.execute("ALTER TABLE ai_refine_runs ADD COLUMN current_recipe_id INTEGER")
        if "current_recipe_name" not in run_columns:
            connection.execute("ALTER TABLE ai_refine_runs ADD COLUMN current_recipe_name TEXT")
        if "current_recipe_started_at" not in run_columns:
            connection.execute("ALTER TABLE ai_refine_runs ADD COLUMN current_recipe_started_at TEXT")
        connection.commit()


def reconcile_interrupted_runs(db_path: Path, model: str) -> None:
    with connect(db_path) as connection:
        connection.execute(
            "UPDATE ai_refine_runs SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE model = ? AND status = 'running'",
            (model,),
        )
        connection.commit()


def count_target_recipes(db_path: Optional[Path]) -> int:
    if db_path is None:
        return 0
    with connect(db_path) as connection:
        return connection.execute("SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'").fetchone()[0]


def load_refine_summary(db_path: Path, model: str, refine_version: str) -> dict:
    with connect(db_path) as connection:
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
            SELECT recipe_id, source_hash, model, last_error
            FROM recipe_ai_refine_state
            WHERE model = ?
            """,
            (model,),
        ).fetchall()

    state_by_recipe = {int(row["recipe_id"]): row for row in state_rows}
    success = 0
    failed = 0
    pending = 0
    for recipe in recipes:
        recipe_id = int(recipe["id"])
        state = state_by_recipe.get(recipe_id)
        if state is None or (state["source_hash"] or "") != (recipe["source_hash"] or ""):
            pending += 1
            continue
        if (state["last_error"] or "").strip():
            failed += 1
            pending += 1
            continue
        if has_suspicious_refined_ingredients(db_path, recipe_id):
            pending += 1
        else:
            success += 1

    return {
        "total": len(recipes),
        "success": success,
        "failed": failed,
        "pending": pending,
    }


def load_latest_run_status(db_path: Path, model: str) -> Optional[sqlite3.Row]:
    with connect(db_path) as connection:
        return connection.execute(
            "SELECT * FROM ai_refine_runs WHERE model = ? ORDER BY id DESC LIMIT 1",
            (model,),
        ).fetchone()


def format_run_status(status: sqlite3.Row) -> str:
    run_status = str(status["status"] or "")
    if run_status == "running":
        recipe_id = status["current_recipe_id"]
        recipe_name = str(status["current_recipe_name"] or "").strip()
        started_at = str(status["current_recipe_started_at"] or "").strip()
        elapsed = format_elapsed_seconds(started_at)
        label = f"#{recipe_id} {recipe_name}".strip() if recipe_id else "current recipe"
        if elapsed:
            return f"Processing: {label} ({elapsed})"
        return f"Processing: {label}"
    if run_status == "paused":
        return "Paused. Click resume to continue."
    if run_status == "completed":
        return "Completed."
    if run_status == "failed":
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


def load_latest_paused_run(db_path: Optional[Path], model: str) -> Optional[sqlite3.Row]:
    if db_path is None:
        return None
    with connect(db_path) as connection:
        return connection.execute(
            """
            SELECT *
            FROM ai_refine_runs
            WHERE model = ? AND status = 'paused'
            ORDER BY processed_count DESC, id DESC
            LIMIT 1
            """,
            (model,),
        ).fetchone()


def load_first_error_message(db_path: Optional[Path], model: str) -> Optional[str]:
    if db_path is None:
        return None
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT last_error
            FROM recipe_ai_refine_state
            WHERE model = ? AND last_error IS NOT NULL AND TRIM(last_error) <> ''
            ORDER BY recipe_id
            LIMIT 1
            """,
            (model,),
        ).fetchone()
    return row["last_error"] if row is not None else None


def load_first_error_raw_response(db_path: Optional[Path], model: str) -> Optional[str]:
    if db_path is None:
        return None
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT last_raw_response
            FROM recipe_ai_refine_state
            WHERE model = ? AND last_raw_response IS NOT NULL AND TRIM(last_raw_response) <> ''
            ORDER BY recipe_id
            LIMIT 1
            """,
            (model,),
        ).fetchone()
    return row["last_raw_response"] if row is not None else None


def create_refine_run(db_path: Path, model: str, refine_version: str) -> int:
    with connect(db_path) as connection:
        total_count = connection.execute("SELECT COUNT(*) FROM recipes WHERE record_kind = 'recipe'").fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO ai_refine_runs (
                model, status, total_count, refine_version, started_at, updated_at
            )
            VALUES (?, 'running', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (model, total_count, refine_version),
        )
        connection.commit()
        return int(cursor.lastrowid)


def set_run_current_recipe(db_path: Path, run_id: int, recipe_id: Optional[int], recipe_name: Optional[str]) -> None:
    with connect(db_path) as connection:
        if recipe_id is None:
            connection.execute(
                """
                UPDATE ai_refine_runs
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
                UPDATE ai_refine_runs
                SET current_recipe_id = ?,
                    current_recipe_name = ?,
                    current_recipe_started_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (recipe_id, recipe_name or "", run_id),
            )
        connection.commit()


def build_refine_version(model: str) -> str:
    payload = {
        "version": REFINE_PROMPT_VERSION,
        "target_fields": ["ingredients"],
        "rule": "keep only ingredient entities, split or mark optional items, never rewrite recipe text fields",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def run_refine_job(
    db_path: Path,
    run_id: int,
    model: str,
    refine_version: str,
    pause_flag_getter: Callable[[], bool],
) -> None:
    try:
        with connect(db_path) as connection:
            run_row = connection.execute(
                "SELECT processed_count, refined_count, skipped_count, error_count FROM ai_refine_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            recipes = connection.execute(
                "SELECT id, name, source_hash FROM recipes WHERE record_kind = 'recipe' ORDER BY id"
            ).fetchall()

        pending_recipes = []
        skipped_count = 0
        for recipe_row in recipes:
            recipe_id = int(recipe_row["id"])
            source_hash = recipe_row["source_hash"] or ""
            if should_skip_recipe(db_path, recipe_id, source_hash, model, refine_version):
                skipped_count += 1
            else:
                pending_recipes.append(recipe_row)

        processed_count = 0
        refined_count = 0
        error_count = 0
        reset_run_for_pending_work(
            db_path,
            run_id,
            total_count=len(pending_recipes),
            processed_count=processed_count,
            refined_count=refined_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )

        for recipe_row in pending_recipes:
            if pause_flag_getter():
                mark_run_paused(db_path, run_id)
                return

            recipe_id = int(recipe_row["id"])
            recipe_name = str(recipe_row["name"] or "").strip()
            source_hash = recipe_row["source_hash"] or ""
            set_run_current_recipe(db_path, run_id, recipe_id, recipe_name)

            try:
                snapshot = load_recipe_snapshot(db_path, recipe_id)
                snapshot["source_hash"] = source_hash
                result = generate_refined_recipe(snapshot, model)
                apply_refined_recipe(db_path, recipe_id, result)
                store_refine_snapshot(
                    db_path,
                    recipe_id=recipe_id,
                    run_id=run_id,
                    model=model,
                    refine_version=refine_version,
                    before_ingredients=snapshot["ingredients"],
                    after_ingredients=result["ingredients"],
                )
                upsert_refine_state(
                    db_path,
                    recipe_id=recipe_id,
                    source_hash=source_hash,
                    model=model,
                    refine_version=refine_version,
                    run_id=run_id,
                    last_error=None,
                    last_raw_response=None,
                )
                refined_count += 1
                processed_count += 1
                update_run_progress(db_path, run_id, "running", processed_count, refined_count, skipped_count, error_count)
            except Exception as error:
                error_count += 1
                raw_response = getattr(error, "raw_response", None)
                upsert_refine_state(
                    db_path,
                    recipe_id=recipe_id,
                    source_hash=source_hash,
                    model=model,
                    refine_version=refine_version,
                    run_id=run_id,
                    last_error=str(error),
                    last_raw_response=raw_response,
                )
                processed_count += 1
                update_run_progress(db_path, run_id, "running", processed_count, refined_count, skipped_count, error_count)

        complete_run(db_path, run_id, refined_count, skipped_count, error_count)
    except Exception as error:
        fail_run(db_path, run_id, str(error))


def mark_run_paused(db_path: Path, run_id: int) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ai_refine_runs
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


def update_run_progress(
    db_path: Path,
    run_id: int,
    status: str,
    processed_count: int,
    refined_count: int,
    skipped_count: int,
    error_count: int,
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ai_refine_runs
            SET status = ?, processed_count = ?, refined_count = ?, skipped_count = ?, error_count = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, processed_count, refined_count, skipped_count, error_count, run_id),
        )
        connection.commit()


def reset_run_for_pending_work(
    db_path: Path,
    run_id: int,
    *,
    total_count: int,
    processed_count: int,
    refined_count: int,
    skipped_count: int,
    error_count: int,
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ai_refine_runs
            SET status = 'running',
                total_count = ?,
                processed_count = ?,
                refined_count = ?,
                skipped_count = ?,
                error_count = ?,
                current_recipe_id = NULL,
                current_recipe_name = NULL,
                current_recipe_started_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (total_count, processed_count, refined_count, skipped_count, error_count, run_id),
        )
        connection.commit()


def complete_run(db_path: Path, run_id: int, refined_count: int, skipped_count: int, error_count: int) -> None:
    with connect(db_path) as connection:
        total_count = connection.execute("SELECT total_count FROM ai_refine_runs WHERE id = ?", (run_id,)).fetchone()[0]
        connection.execute(
            """
            UPDATE ai_refine_runs
            SET status = 'completed',
                processed_count = ?,
                refined_count = ?,
                skipped_count = ?,
                error_count = ?,
                current_recipe_id = NULL,
                current_recipe_name = NULL,
                current_recipe_started_at = NULL,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (total_count, refined_count, skipped_count, error_count, run_id),
        )
        connection.commit()


def fail_run(db_path: Path, run_id: int, error_message: str) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE ai_refine_runs
            SET status = 'failed',
                current_recipe_id = NULL,
                current_recipe_name = NULL,
                current_recipe_started_at = NULL,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE id = ?
            """,
            (error_message, run_id),
        )
        connection.commit()


def should_skip_recipe(db_path: Path, recipe_id: int, source_hash: str, model: str, refine_version: str) -> bool:
    with connect(db_path) as connection:
        state = connection.execute(
            "SELECT source_hash, model, refine_version, last_error FROM recipe_ai_refine_state WHERE recipe_id = ?",
            (recipe_id,),
        ).fetchone()
    if state is None:
        return False
    state_matches = (
        (state["source_hash"] or "") == source_hash
        and (state["model"] or "") == model
        and not (state["last_error"] or "").strip()
    )
    if not state_matches:
        return False
    return not has_suspicious_refined_ingredients(db_path, recipe_id)


def has_suspicious_refined_ingredients(db_path: Path, recipe_id: int) -> bool:
    """Return True when a previous "successful" result should be refined again."""
    with connect(db_path) as connection:
        recipe_row = connection.execute(
            """
            SELECT ingredients_text, seasonings_text
            FROM recipes
            WHERE id = ?
            """,
            (recipe_id,),
        ).fetchone()
        ingredient_rows = connection.execute(
            """
            SELECT i.name, i.normalized_name, ri.amount, ri.unit, ri.remark
            FROM recipe_ingredients ri
            INNER JOIN ingredients i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY ri.id
            """,
            (recipe_id,),
        ).fetchall()

    if recipe_row is None:
        return True

    source_text = " ".join(
        part.strip()
        for part in [recipe_row["ingredients_text"] or "", recipe_row["seasonings_text"] or ""]
        if part and part.strip()
    )
    if not source_text:
        return False

    for row in ingredient_rows:
        name = (row["normalized_name"] or row["name"] or "").strip()
        amount = (row["amount"] or "").strip()
        unit = (row["unit"] or "").strip()
        remark = (row["remark"] or "").strip()
        if is_suspicious_refined_item(name, amount, unit, remark):
            return True

    source_candidates = count_source_ingredient_candidates(source_text)
    if source_candidates >= 3 and len(ingredient_rows) <= 1:
        return True
    if source_candidates >= 6 and len(ingredient_rows) <= 2:
        return True
    return False


def count_source_ingredient_candidates(source_text: str) -> int:
    compact = re.sub(r"\s+", "", source_text or "")
    if not compact:
        return 0
    parts = [
        part.strip()
        for part in re.split(r"[\u3001\uff0c\uff1b,;/\n]+", compact)
        if part.strip()
    ]
    useful_parts = [
        part
        for part in parts
        if len(part) <= 28 and not any(hint in part for hint in DROP_HINTS)
    ]
    return len(useful_parts)


def is_suspicious_refined_item(name: str, amount: str, unit: str, remark: str) -> bool:
    compact = re.sub(r"\s+", "", name or "")
    if should_drop_name(compact):
        return True
    if re.search(r"\d", compact):
        return True
    if re.search(r"[\r\n:：;；。.!?？]", compact):
        return True
    if any(term in compact for term in ("\u914d\u7ea6", "\u66f4\u597d\u5403", "\u53ef\u52a0", "\u5efa\u8bae")):
        return True
    if (amount or "").strip() and (unit or "").strip() and AMOUNT_WITH_UNIT_PATTERN.match((amount or "").strip()):
        return True
    return False


def upsert_refine_state(
    db_path: Path,
    *,
    recipe_id: int,
    source_hash: str,
    model: str,
    refine_version: str,
    run_id: int,
    last_error: Optional[str],
    last_raw_response: Optional[str] = None,
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO recipe_ai_refine_state (
                recipe_id, source_hash, model, refine_version, refined_at, last_run_id, last_error, last_raw_response
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            ON CONFLICT(recipe_id) DO UPDATE SET
                source_hash = excluded.source_hash,
                model = excluded.model,
                refine_version = excluded.refine_version,
                refined_at = CURRENT_TIMESTAMP,
                last_run_id = excluded.last_run_id,
                last_error = excluded.last_error,
                last_raw_response = excluded.last_raw_response
            """,
            (recipe_id, source_hash, model, refine_version, run_id, last_error, last_raw_response),
        )
        connection.commit()


def store_refine_snapshot(
    db_path: Path,
    *,
    recipe_id: int,
    run_id: int,
    model: str,
    refine_version: str,
    before_ingredients: List[dict],
    after_ingredients: List[dict],
) -> None:
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO recipe_refine_snapshots (
                recipe_id,
                run_id,
                model,
                refine_version,
                before_ingredients_json,
                after_ingredients_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                recipe_id,
                run_id,
                model,
                refine_version,
                json.dumps(before_ingredients, ensure_ascii=False),
                json.dumps(after_ingredients, ensure_ascii=False),
            ),
        )
        connection.commit()


def load_recipe_snapshot(db_path: Path, recipe_id: int) -> dict:
    with connect(db_path) as connection:
        recipe_row = connection.execute(
            """
            SELECT
                id, name, library_section, section_name, cuisine, sub_cuisine,
                ingredients_text, seasonings_text
            FROM recipes
            WHERE id = ?
            """,
            (recipe_id,),
        ).fetchone()
        ingredient_rows = connection.execute(
            """
            SELECT i.name, ri.amount, ri.unit, ri.remark
            FROM recipe_ingredients ri
            INNER JOIN ingredients i ON i.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY ri.id
            """,
            (recipe_id,),
        ).fetchall()

    if recipe_row is None:
        raise ValueError(f"Recipe not found: {recipe_id}")

    return {
        "id": recipe_row["id"],
        "name": recipe_row["name"] or "",
        "library_section": recipe_row["library_section"] or "",
        "section_name": recipe_row["section_name"] or "",
        "cuisine": recipe_row["cuisine"] or "",
        "sub_cuisine": recipe_row["sub_cuisine"] or "",
        "ingredients_text": recipe_row["ingredients_text"] or "",
        "seasonings_text": recipe_row["seasonings_text"] or "",
        "ingredients": [
            {
                "name": row["name"] or "",
                "amount": row["amount"] or "",
                "unit": row["unit"] or "",
                "remark": row["remark"] or "",
            }
            for row in ingredient_rows
        ],
    }


def generate_refined_recipe(recipe: dict, model: str) -> dict:
    if not has_source_for_model_refine(recipe):
        return {"ingredients": []}

    response_text = call_ollama_chat(model, build_refine_messages(recipe), response_format=INGREDIENT_JSON_SCHEMA)
    parse_error: Optional[Exception] = None
    ingredients: List[dict] = []
    try:
        payload = extract_json_payload(response_text)
        ingredients = sanitize_ingredients(payload.get("ingredients"))
    except Exception as error:
        parse_error = error
    if not ingredients:
        ingredients = fallback_ingredients_from_source(recipe)
    if not ingredients and (recipe["ingredients_text"] or recipe["ingredients"]):
        error = RuntimeError(
            "Model did not return usable ingredient entities"
            if parse_error is not None
            else "Model returned no usable ingredient entities"
        )
        setattr(error, "raw_response", response_text)
        raise error
    return {"ingredients": ingredients}


def has_source_for_model_refine(recipe: dict) -> bool:
    text = " ".join(
        str(recipe.get(key) or "").strip()
        for key in ("ingredients_text", "seasonings_text")
    ).strip()
    if text:
        return True
    return bool(recipe.get("ingredients"))


def build_refine_messages(recipe: dict) -> List[dict]:
    compact_payload = {
        "name": recipe.get("name", ""),
        "library_section": recipe.get("library_section", ""),
        "section_name": recipe.get("section_name", ""),
        "ingredients_text": recipe.get("ingredients_text", ""),
        "seasonings_text": recipe.get("seasonings_text", ""),
    }
    prompt = "\n".join(
        [
            "/no_think",
            "Do not output thinking, analysis, explanation, or chain-of-thought.",
            "Output the final JSON object immediately.",
            "",
            "Extract only structured ingredient entities from the recipe.",
            "Only use ingredients_text and seasonings_text.",
            "Ignore cooking steps. Do not infer ingredients from dish name alone.",
            "Return JSON only. No prose, no markdown, no code fences.",
            "",
            "Rules:",
            "1. name must be a concrete ingredient entity that can be bought or clearly identified.",
            "2. Drop dish names, flavor descriptions, explanatory sentences, brand slogans, ratio notes, and punctuation fragments.",
            "3. For A/B, A or B, or A(also B), split into multiple ingredient items. Non-primary options use remark='可选'.",
            "4. For phrases like 可加A, 加A更好吃, 可放B, 也可用C, keep only the ingredient name and set remark='可选'.",
            "5. Do not invent ingredients that are not present in the source text.",
            "6. Do not translate Chinese ingredient names into English. Keep the source language.",
            "7. Never output placeholders such as ingredient1, ingredient2, anotheringredient, yetanotheringredient.",
            "8. Never output pure quantities such as 500g as ingredient names.",
            "9. For references such as 见牛肉词条..., return no ingredient unless an actual ingredient name is present outside the reference.",
            "10. Follow the provided JSON schema exactly.",
            "",
            "JSON schema target:",
            json.dumps(INGREDIENT_JSON_SCHEMA, ensure_ascii=False),
            "",
            "Recipe payload:",
            json.dumps(compact_payload, ensure_ascii=False),
        ]
    )
    return [
        {
            "role": "system",
            "content": "/no_think\nYou are a strict ingredient extraction assistant. Output final valid JSON only. Never output thinking or analysis.",
        },
        {"role": "user", "content": prompt},
    ]


def fetch_ollama_models() -> List[str]:
    request = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Ollama unavailable: {error}") from error

    items = payload.get("models")
    if not isinstance(items, list):
        return []

    models = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if name:
            models.append(name)
    return models


def call_ollama_chat(
    model: str,
    messages: List[dict],
    response_format: Optional[object] = None,
    max_attempts: int = OLLAMA_MAX_ATTEMPTS,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        body = json.dumps(
            {
                "model": model,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "thinking": False,
                    "num_ctx": 2048,
                    "num_predict": 1536,
                },
                "messages": messages,
                **({"format": response_format} if response_format is not None else {}),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            OLLAMA_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            message = payload.get("message") or {}
            content = str(message.get("content") or "").strip()
            thinking = str(message.get("thinking") or "").strip()
            if thinking and not content:
                content = thinking
            if not content:
                raise RuntimeError("Ollama returned empty content")
            return content
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            retryable = error.code >= 500 or error.code == 408
            last_error = RuntimeError(f"Ollama HTTP {error.code}: {detail}")
            if not retryable or attempt >= max_attempts:
                raise last_error from error
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = RuntimeError(f"Ollama unavailable: {error}")
            if "timed out" not in str(error).lower() or attempt >= max_attempts:
                raise last_error from error
        except Exception as error:
            last_error = error
            if "timed out" not in str(error).lower() or attempt >= max_attempts:
                raise
        time.sleep(0.6)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Ollama call failed without an error")


def extract_json_payload(response_text: str) -> dict:
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```", 1)[1]
        text = text.rsplit("```", 1)[0]
        text = text.replace("json", "", 1).strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    text = strip_thinking_process(text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"ingredients": parsed}
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    last_payload = None
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            last_payload = parsed
        elif isinstance(parsed, list):
            last_payload = {"ingredients": parsed}

    if last_payload is not None:
        return last_payload

    raise RuntimeError("Model did not return JSON")


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
    last_object = text.rfind('{"ingredients"')
    if last_object >= 0:
        return text[last_object:].strip()
    return text


def sanitize_ingredients(items: object) -> List[dict]:
    if not isinstance(items, list):
        return []

    normalized: List[dict] = []
    seen = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        raw_name, amount, unit, remark = normalize_item_fields(
            str(item.get("name") or "").strip(),
            str(item.get("amount") or "").strip(),
            str(item.get("unit") or "").strip(),
            str(item.get("remark") or "").strip(),
        )

        for split_name, split_amount, split_unit, split_remark in split_choice_name(raw_name, amount, unit, remark):
            name = normalize_name(split_name)
            if not name or should_drop_name(name):
                continue

            key = (name, split_amount, split_unit, split_remark)
            if key in seen:
                continue
            seen.add(key)
            normalized.append({"name": name, "amount": split_amount, "unit": split_unit, "remark": split_remark})

    return normalized


def fallback_ingredients_from_source(recipe: dict) -> List[dict]:
    text = "，".join(
        part.strip()
        for part in [
            recipe.get("ingredients_text") or "",
            recipe.get("seasonings_text") or "",
        ]
        if part and part.strip()
    )
    if not text:
        return []

    raw_parts = [part.strip() for part in FALLBACK_SPLIT_PATTERN.split(text) if part.strip()]
    if not raw_parts:
        raw_parts = [text]
    if len(raw_parts) > 48:
        return []

    candidates: List[dict] = []
    for raw_part in raw_parts:
        cleaned_part = clean_fallback_part(raw_part)
        if not cleaned_part:
            continue
        if len(cleaned_part) > 24:
            continue
        candidates.append({"name": cleaned_part, "amount": "", "unit": "", "remark": ""})

    sanitized = sanitize_ingredients(candidates)
    if sanitized:
        return sanitized

    if len(raw_parts) == 1 and len(raw_parts[0]) <= 40 and FALLBACK_CHOICE_PATTERN.search(raw_parts[0]):
        return sanitize_ingredients([{"name": raw_parts[0], "amount": "", "unit": "", "remark": ""}])

    return []


def clean_fallback_part(raw_part: str) -> str:
    text = str(raw_part or "").strip()
    text = re.sub(r"[【\[].*?[】\]]", "", text)
    text = re.sub(r"^[^：:]{1,12}[：:]", "", text)
    text = re.sub(r"（[^）]{0,30}）", "", text)
    text = re.sub(r"\([^)]{0,30}\)", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip(" ,，、。；;:：")


def normalize_item_fields(name: str, amount: str, unit: str, remark: str) -> Tuple[str, str, str, str]:
    candidate = re.sub(r"\s+", "", name or "")
    candidate = re.sub(r"[()（）\[\]【】]", "", candidate)
    amount, unit = normalize_amount_unit(amount, unit)
    candidate, amount, unit = split_trailing_amount(candidate, amount, unit)
    candidate = strip_known_prefixes(candidate)
    candidate, amount, unit, remark = extract_amount_from_name(candidate, amount, unit, remark)
    candidate = extract_named_fragment(candidate)
    return candidate, amount, unit, remark


def normalize_amount_unit(amount: str, unit: str) -> Tuple[str, str]:
    clean_amount = re.sub(r"\s+", "", amount or "")
    clean_unit = re.sub(r"\s+", "", unit or "")
    match = AMOUNT_WITH_UNIT_PATTERN.match(clean_amount)
    if match:
        parsed_unit = match.group("unit")
        if not clean_unit or clean_unit.lower() == parsed_unit.lower():
            clean_amount = match.group("amount")
            clean_unit = parsed_unit
    return clean_amount, clean_unit


def split_trailing_amount(name: str, amount: str, unit: str) -> Tuple[str, str, str]:
    if amount or unit:
        return name, amount, unit
    match = TRAILING_AMOUNT_PATTERN.match(name)
    if not match:
        return name, amount, unit
    candidate_name = (match.group("name") or "").strip()
    if not candidate_name:
        return name, amount, unit
    return candidate_name, match.group("amount"), match.group("unit")


def split_choice_name(name: str, amount: str, unit: str, remark: str) -> List[Tuple[str, str, str, str]]:
    extracted_name, extracted_remark = extract_optional_name(name, remark)
    if re.search(r"(?:/|／|\\|or|OR|或)", extracted_name):
        parts = [part.strip() for part in re.split(r"(?:/|／|\\|or|OR|或)", extracted_name) if part.strip()]
        items: List[Tuple[str, str, str, str]] = []
        for index, part in enumerate(parts):
            items.append((part, amount, unit, "" if index == 0 else merge_remarks("可选", extracted_remark)))
        return items

    segmented = segment_compound_name(extracted_name)
    if len(segmented) > 1:
        return [(part, amount, unit, extracted_remark) for part in segmented]

    return [(extracted_name, amount, unit, extracted_remark)]


def strip_known_prefixes(text: str) -> str:
    candidate = text
    for prefix in BRAND_PREFIXES:
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            candidate = candidate[len(prefix) :]
            break
    for prefix in GENERIC_PREFIXES:
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            candidate = candidate[len(prefix) :]
            break
    return candidate


def extract_amount_from_name(text: str, amount: str, unit: str, remark: str) -> Tuple[str, str, str, str]:
    if amount or unit:
        return text, amount, unit, remark

    match = AMOUNT_IN_NAME_PATTERN.search(text)
    if not match:
        return text, amount, unit, remark

    new_name = match.group("prefix").strip()
    package_hint = ""
    package_match = PACKAGE_HINT_PATTERN.search(new_name)
    if package_match:
        package_hint = package_match.group(1)
        new_name = new_name[: -len(package_hint)].strip()

    return new_name, match.group("amount"), match.group("unit"), merge_remarks(package_hint, remark)


def extract_named_fragment(text: str) -> str:
    if "用的" in text:
        text = text.split("用的", 1)[1]
    elif "用" in text and len(text.split("用", 1)[1]) >= 2:
        text = text.split("用", 1)[1]
    return text


def segment_compound_name(text: str) -> List[str]:
    candidate = text.strip()
    results: List[str] = []
    remaining = candidate

    while remaining:
        matched = False
        for segment in sorted(INGREDIENT_SEGMENTS, key=len, reverse=True):
            if remaining.startswith(segment):
                results.append(segment)
                remaining = remaining[len(segment) :]
                matched = True
                break
        if not matched:
            return [candidate]
    return results if results else [candidate]


def extract_optional_name(text: str, remark: str) -> Tuple[str, str]:
    candidate = text.strip(" ,，。；;:：()（）[]【】")
    merged_remark = remark.strip()
    for prefix in OPTIONAL_PREFIXES:
        if candidate.startswith(prefix) and len(candidate) > len(prefix):
            return candidate[len(prefix):].strip(), merge_remarks("可选", merged_remark)
    for suffix in OPTIONAL_SUFFIXES:
        if candidate.endswith(suffix) and len(candidate) > len(suffix):
            return candidate[: -len(suffix)].strip(), merge_remarks("可选", merged_remark)
    return candidate, merged_remark


def merge_remarks(primary: str, secondary: str) -> str:
    first = primary.strip()
    second = secondary.strip()
    if not first:
        return second
    if not second or second == first or second in first:
        return first
    return f"{first} / {second}"


def normalize_name(name: str) -> str:
    compact = re.sub(r"\s+", "", name.strip())
    compact = re.sub(r"[()（）\[\]【】]", "", compact)
    compact = compact.strip(" ,，。；;:：+-*/")
    return INGREDIENT_ALIASES.get(compact, normalize_ingredient_name(compact))


def normalize_ingredient_name(name: str) -> str:
    return name


def should_drop_name(name: str) -> bool:
    compact = re.sub(r"\s+", "", name or "")
    if not compact or len(compact) > 20 or compact in {"%", "％", "1"}:
        return True
    if AMOUNT_WITH_UNIT_PATTERN.match(compact) or re.fullmatch(r"\d+(?:\.\d+)?", compact):
        return True
    if re.search(r"[A-Za-z]", compact):
        return True
    return any(hint in compact for hint in DROP_HINTS)


def apply_refined_recipe(db_path: Path, recipe_id: int, refined: dict) -> None:
    with connect(db_path) as connection:
        connection.execute("UPDATE recipes SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (recipe_id,))
        connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))

        for item in refined["ingredients"]:
            ingredient_id = get_or_create_ingredient(connection, item["name"])
            connection.execute(
                """
                INSERT INTO recipe_ingredients (recipe_id, ingredient_id, amount, unit, remark)
                VALUES (?, ?, ?, ?, ?)
                """,
                (recipe_id, ingredient_id, item["amount"] or None, item["unit"] or None, item["remark"] or None),
            )

        connection.execute(
            "DELETE FROM ingredients WHERE id NOT IN (SELECT DISTINCT ingredient_id FROM recipe_ingredients)"
        )
        connection.commit()


def get_or_create_ingredient(connection: sqlite3.Connection, name: str) -> int:
    normalized_name = normalize_name(name)
    row = connection.execute(
        "SELECT id FROM ingredients WHERE normalized_name = ? OR name = ? ORDER BY id LIMIT 1",
        (normalized_name, normalized_name),
    ).fetchone()
    if row is not None:
        return int(row["id"])

    cursor = connection.execute(
        "INSERT INTO ingredients (name, alias, normalized_name) VALUES (?, NULL, ?)",
        (normalized_name, normalized_name),
    )
    return int(cursor.lastrowid)


def main() -> None:
    root = Tk()
    ttk.Style().theme_use("vista")
    RecipeDbRefinerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
