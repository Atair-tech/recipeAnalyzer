# Recipe Analyzer

本项目是一个围绕真实菜谱 Excel 工作簿构建的本地菜谱库。核心定位不是通用 Excel 查看器，而是把菜谱工作簿同步到本地 SQLite 数据库后，提供浏览、筛选、分析、AI 辅助整理和数据库管理能力。

## 当前原则

- `Excel` 是主数据源。
- `SQLite` 是程序实际使用的本地数据库。
- Web 端以浏览、检索、分析、AI 辅助处理和数据库管理为主。
- AI 生成内容仅供参考；原始 Excel 中的食材、调料、做法及要点始终是最终依据。

## 当前能力

- 同步 `data/recipes.xlsx` 到本地数据库。
- 按差异同步菜谱数据：新增、更新、删除、未变化。
- 浏览菜谱、查看详情、导出筛选结果。
- 按专题库、分组、菜系、可见标准化食材、自动标签、BMD、CC 筛选。
- 总览仪表盘和多维度统计。
- 菜谱配对审查、数据库表格浏览、整库导入导出。
- step1 本地 AI 分析食材：抽取标准化食材，不改写原始菜谱文本。
- step2 外部 AI 剔除杂乱项：默认使用 DeepSeek API，只发送食材候选词，不发送菜名、做法、备注或完整菜谱。
- 自动标签管理和本地 AI 批量打标签。
- 智能问答：本地 Ollama 问答、自然语言搜索、可选 DeepSeek 前置解析与后处理。
- AI 对话日志查看。
- 独立工具：
  - `desktop/db_refiner/dist/DataHelper.exe`
  - `desktop/db_tagger/dist/LabelHelper.exe`

## 技术栈

- 前端：`React + Vite`
- 后端：`FastAPI`
- 数据库：`SQLite`
- Excel 解析：`openpyxl / pandas`
- 本地模型：`Ollama`
- 可选外部 API：`DeepSeek`

## 本地启动

### 后端

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

开发时可加 `--reload`：

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

```powershell
Set-Location .\frontend
npm install
npm run dev
```

### 访问地址

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## 首次使用流程

1. 启动后端。
2. 启动前端。
3. 访问 `http://127.0.0.1:5173`。
4. 进入 `管理 -> 导入 Excel`，选择 `data/recipes.xlsx` 并同步到 SQLite。
5. 进入 `菜谱库` 浏览和筛选菜谱。
6. 可选：进入 `管理 -> AI分析食材`，执行 step1 和 step2。
7. 可选：进入 `管理 -> 标签管理`，运行自动标签。
8. 交付或迁移前，进入 `管理 -> 查看数据库` 导出当前数据库。

## 页面结构

- `总览`：菜谱库仪表盘和统计分布。
- `菜谱库`：日常浏览、搜索、筛选、查看原文详情。
- `智能问答`：
  - `AI问答`
  - `自然语言搜索`
- `管理`：
  - `标签管理`
  - `导入 Excel`
  - `AI分析食材`
  - `菜谱配对`
  - `查看数据库`
  - `AI 对话记录`
  - `食材审查`

## AI 功能边界

- `标准化食材（AI生成，仅供参考）`：用于筛选、统计和推荐，不覆盖原始 Excel 文本。
- `自动标签（AI生成，仅供参考）`：用于快速筛选和推荐排序，可在标签管理中审查和移除。
- 智能问答基于当前数据库、检索结果和模型能力生成回答，不应视为医学、营养或安全建议。
- DeepSeek 前置解析默认关闭；未配置 API Key 时不会启动外部调用。
- DeepSeek 后处理需要用户手动开启，开启后会发送脱敏候选摘要，可能产生 API 费用。

## 长任务行为

以下任务会在后端后台线程运行：

- step1 本地 AI 分析食材。
- step2 外部 AI 剔除杂乱项。
- 自动标签任务。

说明：

- 可以切换 Web 页面，任务会继续运行。
- 关闭浏览器页面通常不影响任务。
- 关闭后端窗口会中断任务。
- 后端重启时，遗留的 `running` 任务会自动标记为 `paused`，可在页面点击“恢复”继续。

## DeepSeek API Key

配置方式：

- 在 `.env` 中设置 `RECIPE_ANALYZER_DEEPSEEK_API_KEY`。
- 或在 Web 端首次运行 DeepSeek step2 时输入，程序会保存到本机项目根目录 `.env`。

`.env` 不会提交到 GitHub。

可选配置：

```text
RECIPE_ANALYZER_DEEPSEEK_API_KEY=
RECIPE_ANALYZER_DEEPSEEK_MODEL=deepseek-v4-pro
RECIPE_ANALYZER_DEEPSEEK_BASE_URL=https://api.deepseek.com
RECIPE_ANALYZER_DEEPSEEK_REASONING_EFFORT=high
```

## 数据库导入导出

`管理 -> 查看数据库` 支持：

- 导出当前 SQLite 数据库。
- 导入 SQLite 数据库并替换当前数据库。

导入前程序会自动备份当前数据库到 `data/backups/`。仍建议手动保留重要备份。

## 独立工具

`desktop/db_refiner/dist/DataHelper.exe`

- 用于在另一台安装了 Ollama 和本地模型的电脑上处理导出的数据库。
- 直接打开 `.db` 文件。
- 对菜谱做结构化食材 AI 分析。
- 支持暂停、恢复、增量跳过。
- 会直接写回打开的数据库文件。

`desktop/db_tagger/dist/LabelHelper.exe`

- 用于在另一台电脑上对数据库执行自动标签任务。
- 会直接写回打开的数据库文件。

## 交付包建议

不要只交 GitHub 仓库。第一版交付建议同时包含：

- 当前数据库 `.db` 文件。
- 当前 Excel 源文件。
- 启动说明。
- `DataHelper.exe` 和 `LabelHelper.exe`。
- `.env.example`。
- `docs/user-manual.md`。

## 常见问题

- Ollama 未连接：确认 Ollama 已启动，且 `http://127.0.0.1:11434/api/tags` 可访问。
- DeepSeek 未配置 Key：DeepSeek 相关按钮会显示未配置 Key，未输入前不会启动外部调用。
- AI 任务很慢：本地模型速度取决于显卡、模型大小、上下文长度和任务数量。
- 任务被中断：重启后端后任务会显示为暂停，可继续恢复。
- 数据不对：以 Excel 原文为准，AI 生成内容只作为辅助参考。

## 当前边界

- Web 端不是完整编辑器，主数据仍应在 Excel 中维护。
- AI 食材分析和自动标签仍需要人工审查。
- 本地小模型对复杂需求的理解能力有限。
- 外部 API 能提高复杂语义表现，但需要 API Key、网络和费用，并涉及隐私取舍。

## Desktop / Tauri

The first Tauri desktop shell is now scaffolded under `src-tauri/`.

Packaging model:

- Tauri provides the native window.
- The React production build is loaded from `frontend/dist`.
- The FastAPI backend is bundled as a Python sidecar binary.
- Runtime data is stored under `%LOCALAPPDATA%\RecipeAnalyzer\data`.

Build commands:

```powershell
npm install
npm run sidecar:build
npm run frontend:build
npm run tauri:build
```

Or run the full desktop build:

```powershell
npm run desktop:build
```

Tauri requires Rust. If `cargo --version` fails, install Rust from `https://rustup.rs` first.
