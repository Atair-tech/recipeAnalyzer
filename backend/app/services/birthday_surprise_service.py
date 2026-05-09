import json
import os
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.core.config import DATA_DIR


BIRTHDAY_TARGETS = [
    ("20260509_1845", datetime(2026, 5, 9, 18, 45, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1850", datetime(2026, 5, 9, 18, 50, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1857", datetime(2026, 5, 9, 18, 57, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1900", datetime(2026, 5, 9, 19, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1908", datetime(2026, 5, 9, 19, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1912", datetime(2026, 5, 9, 19, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1918", datetime(2026, 5, 9, 19, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1922", datetime(2026, 5, 9, 19, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1928", datetime(2026, 5, 9, 19, 28, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_1932", datetime(2026, 5, 9, 19, 32, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_2000", datetime(2026, 5, 9, 20, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_2010", datetime(2026, 5, 9, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260509_2020", datetime(2026, 5, 9, 20, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260510_0000", datetime(2026, 5, 10, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), True),
    ("20260510_0930", datetime(2026, 5, 10, 9, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
    ("20260510_1000", datetime(2026, 5, 10, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")), False),
]
BIRTHDAY_CATCH_UP_WINDOW = timedelta(hours=12)
BIRTHDAY_TEST_GRACE = timedelta(seconds=20)
BIRTHDAY_EVENT_FILE = DATA_DIR / "birthday_surprise_event.json"
BIRTHDAY_FRONTEND_URL = "http://127.0.0.1:5173/#birthday"

_started = False


def start_birthday_surprise_scheduler() -> None:
    global _started
    if _started:
        return
    _started = True

    targets = ", ".join(f"{trigger_id}={target.isoformat()}" for trigger_id, target, _ in BIRTHDAY_TARGETS)
    _write_status_log(f"scheduler starting; targets={targets}")
    for trigger_id, target, allow_catch_up in BIRTHDAY_TARGETS:
        thread = threading.Thread(
            target=_run_scheduler,
            args=(trigger_id, target, allow_catch_up),
            name=f"birthday-surprise-scheduler-{trigger_id}",
            daemon=True,
        )
        thread.start()


def get_pending_birthday_surprise_event() -> dict:
    try:
        payload = json.loads(BIRTHDAY_EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pending": False}
    return {"pending": True, **payload}


def acknowledge_birthday_surprise_event(event_id: str) -> dict:
    try:
        payload = json.loads(BIRTHDAY_EVENT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pending": False}

    if payload.get("event_id") == event_id:
        BIRTHDAY_EVENT_FILE.unlink(missing_ok=True)
        _write_status_log(f"frontend acknowledged event; event_id={event_id}")
        return {"pending": False}

    return {"pending": True, **payload}


def _run_scheduler(trigger_id: str, target: datetime, allow_catch_up: bool) -> None:
    done_flag = _done_flag_for(trigger_id)
    now = _now()
    if done_flag.exists():
        _write_status_log(f"{trigger_id} skipped; done flag already exists")
        return
    catch_up_window = BIRTHDAY_CATCH_UP_WINDOW if allow_catch_up else BIRTHDAY_TEST_GRACE
    if now > target + catch_up_window:
        _write_status_log(f"{trigger_id} skipped; missed trigger window; now={now.isoformat()}")
        return

    if now < target:
        _write_status_log(f"{trigger_id} waiting; target={target.isoformat()}; now={now.isoformat()}")
        _sleep_until(target)

    if done_flag.exists():
        _write_status_log(f"{trigger_id} skipped after wait; done flag already exists")
        return

    _write_status_log(f"{trigger_id} triggering; now={_now().isoformat()}")
    try:
        _show_continue_dialog()
    except Exception as error:
        _write_error_log(f"{trigger_id}:dialog", error)
        _show_fallback_message_box()

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        done_flag.write_text(_now().isoformat(), encoding="utf-8")
    except Exception as error:
        _write_error_log(f"{trigger_id}:done-flag", error)

    try:
        _publish_frontend_event(trigger_id, target)
        _open_frontend(trigger_id)
    except Exception as error:
        _write_error_log(f"{trigger_id}:open-frontend", error)


def _sleep_until(target: datetime) -> None:
    while True:
        remaining_seconds = (target - _now()).total_seconds()
        if remaining_seconds <= 0:
            return
        time.sleep(min(remaining_seconds, 60))


def _show_continue_dialog() -> None:
    try:
        import tkinter as tk
    except Exception:
        _show_fallback_message_box()
        return

    root = tk.Tk()
    root.title("Recipe Analyzer")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    root.configure(bg="#fff7ef")

    width = 360
    height = 170
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = int((screen_width - width) / 2)
    y = int((screen_height - height) / 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    label = tk.Label(
        root,
        text="生日快乐！",
        font=("Microsoft YaHei UI", 24, "bold"),
        bg="#fff7ef",
        fg="#2f261d",
    )
    label.pack(expand=True, fill="both", padx=24, pady=(24, 10))

    button = tk.Button(
        root,
        text="继续",
        font=("Microsoft YaHei UI", 12),
        command=root.destroy,
        width=12,
        bg="#2f6c5c",
        fg="#ffffff",
        activebackground="#245448",
        activeforeground="#ffffff",
    )
    button.pack(pady=(0, 22))

    root.lift()
    root.focus_force()
    root.mainloop()


def _show_fallback_message_box() -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, "生日快乐！", "Recipe Analyzer", 0x00040000)
    except Exception:
        return


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _done_flag_for(trigger_id: str) -> Path:
    if trigger_id == "20260510_0000":
        return DATA_DIR / "birthday_surprise_2026.done"
    return DATA_DIR / f"birthday_surprise_{trigger_id}.done"


def _publish_frontend_event(trigger_id: str, target: datetime) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_id": f"{trigger_id}-{int(time.time())}",
        "trigger_id": trigger_id,
        "route": "birthday",
        "created_at": _now().isoformat(),
        "target_at": target.isoformat(),
    }
    BIRTHDAY_EVENT_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    _write_status_log(f"{trigger_id} published frontend event; event_id={payload['event_id']}")


def _open_frontend(trigger_id: str) -> None:
    desktop_exe = os.getenv("RECIPE_ANALYZER_DESKTOP_EXE", "").strip()
    if desktop_exe:
        desktop_path = Path(desktop_exe)
        if desktop_path.exists():
            environment = os.environ.copy()
            environment["RECIPE_ANALYZER_PRESERVE_BACKEND"] = "1"
            creation_flags = 0x08000000 if os.name == "nt" else 0
            subprocess.Popen(
                [str(desktop_path)],
                cwd=str(desktop_path.parent),
                env=environment,
                creationflags=creation_flags,
            )
            _write_status_log(f"{trigger_id} opened desktop frontend; exe={desktop_path}")
            return

    webbrowser.open(BIRTHDAY_FRONTEND_URL)
    _write_status_log(f"{trigger_id} opened web frontend; url={BIRTHDAY_FRONTEND_URL}")


def _write_error_log(stage: str, error: Exception) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DATA_DIR / "birthday_surprise_error.log"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat()} [{stage}] {error!r}\n")
    except Exception:
        return


def _write_status_log(message: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        log_path = DATA_DIR / "birthday_surprise_status.log"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat()} {message}\n")
    except Exception:
        return
