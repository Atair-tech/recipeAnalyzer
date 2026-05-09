from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.__main__ import run
from PyInstaller.utils.win32 import winutils


def _noop(*_args, **_kwargs) -> None:
    return None


def main() -> None:
    # Some Windows security tools lock newly generated PyInstaller executables
    # exactly when PyInstaller rewrites PE timestamp/checksum metadata. These
    # metadata edits are optional for our local sidecar, so skip them to make
    # release builds deterministic on stricter machines.
    winutils.set_exe_build_timestamp = _noop
    winutils.update_exe_pe_checksum = _noop

    root = Path(__file__).resolve().parents[2]
    run(
        [
            "--noconfirm",
            "--onefile",
            "--noconsole",
            "--clean",
            "--name",
            "recipe-backend-x86_64-pc-windows-msvc",
            "--distpath",
            "dist",
            "--workpath",
            "build",
            "--specpath",
            "build",
            "--paths",
            str(root / "backend"),
            "recipe_backend_sidecar.py",
        ]
    )


if __name__ == "__main__":
    sys.exit(main())
