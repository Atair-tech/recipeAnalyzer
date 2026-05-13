import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_JSON = ROOT / "package.json"
NSIS_DIR = ROOT / "src-tauri" / "target" / "release" / "bundle" / "nsis"
OWNER = "Atair-tech"
REPO = "recipeAnalyzer"


def main() -> None:
    package_data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    version = package_data["version"]
    installer_name = f"Recipe Analyzer_{version}_x64-setup.exe"
    installer_path = NSIS_DIR / installer_name
    signature_path = NSIS_DIR / f"{installer_name}.sig"
    output_path = NSIS_DIR / "latest.json"

    if not installer_path.exists():
        raise FileNotFoundError(installer_path)
    if not signature_path.exists():
        raise FileNotFoundError(signature_path)

    # GitHub release assets normalize spaces in file names to dots.
    github_asset_name = installer_name.replace(" ", ".")
    asset_name = quote(github_asset_name)
    payload = {
        "version": version,
        "notes": f"Recipe Analyzer {version}",
        "pub_date": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "platforms": {
            "windows-x86_64": {
                "signature": signature_path.read_text(encoding="utf-8").strip(),
                "url": f"https://github.com/{OWNER}/{REPO}/releases/download/v{version}/{asset_name}",
            }
        },
    }

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
