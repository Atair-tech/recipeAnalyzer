# Label Helper

Standalone tag testing tool for exported SQLite databases.

Behavior:
- Reads an exported `.db / .sqlite / .sqlite3`
- Loads local Ollama models and lets the user choose one
- Applies the same managed-tag selection logic as the main app
- Saves results back into the selected database file after each recipe
- Supports pause and resume
- Skips unchanged recipes when `source_hash + model + tag_version` matches and the previous run did not fail

Prerequisites:
- Windows
- Ollama running locally
- A local model installed, preferably `qwen3:4b`
- A database exported from the main app

Run from source:

```powershell
python desktop/db_tagger/recipe_db_tagger.py
```

Build exe:

```powershell
desktop\db_tagger\build_exe.bat
```
