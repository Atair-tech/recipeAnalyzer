import os
from pathlib import Path
from typing import Iterable


def load_local_env() -> None:
    """Load local .env files without adding a runtime dependency.

    Existing process environment variables take precedence. This keeps server
    deployment behavior predictable while allowing local API keys to live
    outside source-controlled code.
    """
    for env_path in _candidate_env_paths():
        if env_path.exists():
            _load_env_file(env_path)


def is_env_value_configured(key: str) -> bool:
    return bool((os.getenv(key) or "").strip())


def save_local_env_value(key: str, value: str) -> Path:
    """Persist a local env value to repo-root .env and update this process."""
    clean_key = key.strip()
    clean_value = value.strip()
    if not clean_key:
        raise ValueError("Environment variable key is required")
    if "\n" in clean_value or "\r" in clean_value:
        raise ValueError("Environment variable value must be one line")

    env_path = _candidate_env_paths()[0]
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    next_lines = _replace_or_append_env_line(existing_lines, clean_key, clean_value)
    env_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    os.environ[clean_key] = clean_value
    return env_path


def _candidate_env_paths() -> list[Path]:
    app_root = Path(__file__).resolve().parents[1]
    backend_root = app_root.parent
    repo_root = backend_root.parent
    return [repo_root / ".env", backend_root / ".env"]


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_inline_comment(value.strip())
        if not key or key in os.environ:
            continue
        os.environ[key] = _unquote(value)


def _replace_or_append_env_line(lines: Iterable[str], key: str, value: str) -> list[str]:
    next_lines: list[str] = []
    replaced = False
    for raw_line in lines:
        line = raw_line.strip()
        candidate = line[len("export ") :].strip() if line.startswith("export ") else line
        if "=" in candidate and candidate.split("=", 1)[0].strip() == key:
            next_lines.append(f"{key}={_quote_env_value(value)}")
            replaced = True
        else:
            next_lines.append(raw_line)
    if not replaced:
        next_lines.append(f"{key}={_quote_env_value(value)}")
    return next_lines


def _quote_env_value(value: str) -> str:
    if not value:
        return ""
    if any(char.isspace() for char in value) or "#" in value or '"' in value or "'" in value:
        return json_escape(value)
    return value


def json_escape(value: str) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def _strip_inline_comment(value: str) -> str:
    if not value or value[0] in {"'", '"'}:
        return value
    comment_index = value.find(" #")
    if comment_index >= 0:
        return value[:comment_index].rstrip()
    return value


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
