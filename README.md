# Recipe Analyzer

本项目是一个围绕真实菜谱工作簿构建的本地菜谱知识库。  
当前原则：

- `Excel` 是主数据源
- `SQLite` 是程序实际使用的本地数据库
- Web 端以浏览、检索、分析、AI 处理和数据库管理为主

## 当前能力

- 同步 `data/recipes.xlsx` 到本地数据库
- 按差异同步菜谱数据：`新增 / 更新 / 删除 / 未变化`
- 浏览菜谱、查看详情、导出筛选结果
- 按专题库、分组、菜系、结构化食材、自动标签等筛选
- 菜谱配对审查
- 结构化食材抽取与 AI 精校
- 结构化食材审查、单条重跑与人工标记
- 自动标签体系、批量 AI 打标与标签审核
- 本地 `Ollama` 智能问答、自然语言搜索、流式阶段展示
- 数据分析仪表盘
- 数据库表格浏览、整库导入、整库导出
- AI 对话日志查看
- 独立数据库精校工具 `desktop/db_refiner/dist/DataHelper.exe`

## 技术栈

- 前端：`React + Vite`
- 后端：`FastAPI`
- 数据库：`SQLite`
- 本地模型：`Ollama`
- 数据处理：`pandas / openpyxl`

## 目录结构

```text
backend/                 FastAPI 后端
frontend/                React 前端
data/                    本地数据库、工作簿、运行时文件
docs/                    项目文档
scripts/                 脚本工具
desktop/db_refiner/      独立数据库精校工具
```

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

## 主要页面

- `总览`
- `菜谱库`
- `智能问答`
- `数据分析`
- `管理`
  - `标签管理`
  - `导入 Excel`
  - `食材审查`
  - `菜谱配对`
  - `查看数据库`
  - `AI 对话记录`

## 智能问答

当前智能问答支持两条路径：

1. `短句快路径`
   适用于 `你好 / 谢谢 / 收到 / 好的` 这类短输入，不走完整检索链路。

2. `检索增强问答`
   先做问题解释，再检索候选菜谱，再调用本地模型生成回答。

当前页面支持：

- 选择本地模型
- 可选是否把当前菜谱作为上下文
- 可选显示推理过程
- 流式展示阶段状态：
  - `正在解释问题`
  - `正在检索菜谱`
  - `正在生成回答`

## AI 精校

当前 `导入 Excel` 页面中的 AI 精校，已经调整为：

- **只精校结构化食材**
- 不再改写：
  - `ingredients_text`
  - `seasonings_text`
  - `steps_text`
  - `notes_text`

精校流程支持：

- 启动
- 暂停
- 恢复
- 增量跳过

增量判断基于：

- `source_hash`
- `model`
- `refine_version`

## 结构化食材审查

`管理 -> 食材审查` 当前支持：

- 查看原始食材文本
- 查看精校前结构化食材快照
- 查看精校后结构化食材快照
- 查看当前结构化食材
- 标记 `通过 / 有问题`
- 保存备注
- 单条重跑精校

注意：

- 精校前后快照只会对新增精校或重跑后的记录开始积累
- 历史旧记录可能没有快照

## 自动标签

系统维护一套独立于 Excel 的自动标签体系：

- 标签定义保存在数据库自带表中
- 不受 Excel 同步覆盖影响
- 可由本地 AI 批量打标签
- 可在 `标签管理` 中审核标签命中结果并手动移除关联

## 数据库导入导出

`管理 -> 查看数据库` 支持：

- 整库导出
- 整库导入

说明：

- 导出的是当前 `SQLite` 数据库文件
- 导入会替换当前数据库内容
- 导入前建议先备份

## 独立精校工具

项目包含一个独立工具：

- `desktop/db_refiner/dist/DataHelper.exe`

用途：

- 在另一台仅安装了 `Ollama` 和本地模型的电脑上
- 直接打开导出的数据库文件
- 对数据库中的菜谱做结构化食材 AI 精校
- 支持暂停、恢复、增量跳过

说明：

- 它会直接写回你打开的那个数据库文件
- 不是内存临时结果

## 当前边界

- Excel 仍然是主数据源，不是 Web 端编辑器
- 本地模型任务可能较慢，尤其是大模型全量精校时
- 自动标签与食材精校的质量仍依赖提示词、规则和人工审查
- `qwen3:4b` 这类本地模型在较长上下文下速度会明显下降

## 相关文档

- 用户手册：[docs/user-manual.md](docs/user-manual.md)
- 下一步规划：[docs/nextsteps0421](docs/nextsteps0421)
