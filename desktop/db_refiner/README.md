# Recipe DB Refiner

独立精校工具。用于在单独机器上直接打开导出的 SQLite 数据库，调用本地 `Ollama + qwen3:4b` 对结构化食材做精校，并把结果持续写回数据库文件。

## 行为

- 只处理 `recipes.record_kind = 'recipe'`
- 已用 `qwen3:4b` 且 `source_hash + refine_version` 未变化的记录会跳过
- 之前由 `qwen3:0.6b` 精校过的记录会重新精校
- 每处理完一条就立即保存回数据库
- 当前版本只重建 `recipe_ingredients`，不改写 `ingredients_text / seasonings_text / steps_text / notes_text`
- 支持暂停和续跑
- 界面只显示总体进度 `a / b`

## 运行前提

- Windows
- 本地已安装并启动 `Ollama`
- 本地已存在模型 `qwen3:4b`
- 需要打开一个导出的数据库文件：`.db / .sqlite / .sqlite3`

## 直接运行源码

```powershell
python desktop/db_refiner/recipe_db_refiner.py
```

## 打包为 exe

仓库里附带了打包脚本：

```powershell
desktop\db_refiner\build_exe.bat
```

脚本会使用仓库根目录 `.venv` 里的 Python 和 PyInstaller 进行打包。打包产物默认输出到：

```text
desktop\db_refiner\dist\RecipeDbRefiner.exe
```
