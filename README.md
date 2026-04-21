# Recipe Analyzer

本项目现在不是“通用 Excel 导入器”，而是围绕真实菜谱工作簿构建的本地菜谱库。

当前栈：

- Frontend: React + Vite
- Backend: FastAPI
- Database: SQLite
- Future desktop shell: Tauri

## 当前实现重点

- 真实工作簿专用导入器
  - 支持“索引页 + 做法页”配对
  - 支持 `甜点配方专区`
  - 支持 `再挑战及待记录`
- 差异同步导入
  - 新增、更新、删除、未变化
- 真实字段入库
  - `专题库`
  - `分组`
  - `菜系 / 亚菜系`
  - `食材 / 调料 / 做法及要点`
  - `BMD / CC`
  - `来源/修订备注`
  - `最后记录日期`
- 浏览器端浏览
  - 按专题库、分组、菜系、食材筛选
  - 只读详情页
  - 导入历史
  - 数据分析
  - 自然语言检索与标签建议基础版

## 目录结构

```text
.
|-- backend/          FastAPI app, SQLite bootstrap, parser, API routes
|-- desktop/          reserved for a future Tauri shell
|-- docs/             architecture notes and user manual
|-- data/             local SQLite database and workbook files
`-- frontend/         React + Vite browser client
```

## 启动方式

### 1. 安装后端依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

### 2. 启动后端

```powershell
Set-Location .\backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. 安装前端依赖

```powershell
Set-Location .\frontend
npm install
```

### 4. 启动前端

```powershell
Set-Location .\frontend
npm run dev
```

打开 `http://127.0.0.1:5173`。

## 当前 API

- `GET /api/health`
- `GET /api/overview`
- `GET /api/recipes`
- `GET /api/recipes/filters`
- `GET /api/recipes/{recipe_id}`
- `PUT /api/recipes/{recipe_id}` 目前固定返回禁用
- `POST /api/imports/preview`
- `POST /api/imports/commit`
- `GET /api/imports/batches`
- `GET /api/imports/batches/{batch_id}`
- `GET /api/analytics/summary`
- `GET /api/ai/natural-search`
- `GET /api/ai/recipes/{recipe_id}/tag-suggestions`

## 导入说明

当前导入器预期的是真实工作簿结构，而不是随意列映射的单表 Excel。

已支持的工作表模式：

- `牛肉 / 牛肉做法`
- `鸡肉 / 鸡肉做法`
- `海鲜 / 海鲜做法`
- `猪肉 / 猪肉做法`
- `羊肉 / 羊肉做法`
- `鸭肉 / 鸭肉做法`
- `其他蛋白质 / 其他蛋白质做法`
- `多种蛋白质及蘸料蘸水 / 多种蛋白质及蘸料蘸水做法`
- `主食及馅料 / 主食及馅料做法`
- `素食 / 素食做法`
- `早餐 / 早餐做法`
- `甜点配方专区`
- `再挑战及待记录`

导入后会把这些信息结构化保存：

- 正式菜谱 / 待办项
- 专题库
- 分组
- 菜名与别名
- 菜系 / 亚菜系
- 最后记录日期
- 来源或修订备注
- BMD / CC 标记
- 食材
- 调料
- 做法及要点

## 当前状态

已实现：

- SQLite 自动初始化与 schema migration
- 真实工作簿专用解析器
- 差异同步导入
- 结构化食材抽取
- 菜谱库列表与只读详情
- 导入历史与批次预览
- 数据分析页
- 自然语言检索基础版
- 标签建议基础版

未实现：

- 回滚到某个导入批次
- Web 端编辑覆盖层
- 稳定外部 ID 列的专用导入支持
- LLM 重排与增量 AI 处理状态

## 下一步建议

1. 在 Excel 中补稳定编号列，降低改名时的匹配风险。
2. 增加 AI 增量状态表，只对新增和变更记录做 AI 处理。
3. 如果浏览流程稳定，再接入 Tauri 做桌面壳。

更多结构说明见 [docs/architecture.md](docs/architecture.md)。
