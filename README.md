# LongDoc Translator Agent

面向论文、技术报告等长文档的结构化翻译 Agent。项目重点不是封装一次 LLM 调用，而是把长文档翻译拆成可解析、可审核、可恢复、可追踪的工程流程。

```text
上传文档
-> 结构化解析与版面修正
-> 结构边界优先的混合切块
-> 术语抽取与人工确认
-> 分块翻译与滑动窗口记忆
-> 检查点恢复
-> 译文、结构资产与风险报告
```

## 当前状态

已经实现：

- FastAPI REST API 与 Gradio 工作台，同一进程运行。
- PostgreSQL 16、SQLAlchemy 2.0、Psycopg 3 和 Alembic。
- Docker Compose 开发库与独立测试库。
- PDF、Markdown、TXT 上传，任务列表、详情、取消和单活动任务约束。
- Docling PDF 解析适配，Markdown/TXT 统一转换为 `ParsedBlock[]`。
- 双栏阅读顺序修正、重复页眉页脚过滤。
- 章节、段落、表格、公式和代码的结构感知切块。
- 大表按完整数据行分组，并保留 caption/header 元数据。
- 表格、公式、引用、长段落和解析异常风险标记。
- Gradio 上传、任务选择、轮询、chunk/术语/风险查看和输出下载入口。
- 真实 PostgreSQL 集成测试。
- DocumentIR Lite、章节树、TableIR/FormulaIR/FigureIR 和 PDF 结构资产。
- target/soft/hard token 预算、本地语义边界和可解释 chunk 字段。
- DeepSeek 术语抽取、术语人工确认和真实翻译。
- LangGraph `StateGraph`、PostgreSQL checkpointer、人工中断和恢复。
- 单任务后台 Worker、进程启动恢复、chunk 边界取消。
- 滑动窗口摘要、分类重试、调用指标和翻译质量检查。
- 工作流节点事件时间线、失败节点展示和节点耗时记录。
- 任务级真实 token 用量与可配置费用预算限制。
- Markdown、HTML、manifest、原始文件与 `result.zip`。

上传任务会由后台 Worker 自动推进到术语确认；用户确认术语后，LangGraph 从原中断点继续翻译。未配置 `LLM_API_KEY` 时，任务会明确进入 `FAILED`，不会回退到 mock 翻译。

仍在开发：

- 高风险 chunk 和章节级人工确认。
- 非 LLM 长耗时节点的协作式超时，以及供应商 fallback。
- 小说模式、长期记忆、专用子图、修订循环和多模型路由。
- OpenTelemetry/LangSmith、replay 数据集和多任务独立 Worker。

## 技术栈

- 后端：Python 3.12、FastAPI、Pydantic
- 数据库：PostgreSQL 16、SQLAlchemy 2.0、Psycopg 3、Alembic
- 前端：Gradio Blocks，挂载于 FastAPI `/ui`
- Agent：LangGraph 1.x、PostgreSQL checkpointer
- 文档解析：Docling、RapidOCR
- LLM：DeepSeek OpenAI-compatible API
- 文件存储：本地文件系统

## 快速开始

要求：

- Python 3.11+，推荐 3.12
- Docker Desktop
- Windows PowerShell
- DeepSeek API Key（调用 LLM 功能时需要）

配置环境：

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

在 `.env` 中填写：

```text
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_deepseek_key
LLM_MODEL=deepseek-v4-flash
JOB_MAX_TOKEN_BUDGET=2000000
JOB_MAX_COST_USD=0
LLM_INPUT_COST_PER_MILLION=0
LLM_OUTPUT_COST_PER_MILLION=0
```

API Key 只能保存在本地 `.env`，不要提交到 Git。
费用上限为 `0` 时禁用费用拦截；如需启用，应按当前 DeepSeek 模型价格填写每百万输入/输出 token 单价。

启动数据库、执行迁移并运行应用：

```powershell
.\scripts\start.ps1
```

也可以逐步运行：

```powershell
docker compose up -d db
cd backend
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

访问：

- Gradio 工作台：<http://127.0.0.1:8000/ui>
- OpenAPI：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

首次解析 PDF 前，可预下载 Docling 模型：

```powershell
.\.venv\Scripts\docling-tools.exe models download layout tableformerv2
```

## 数据库迁移

应用启动只检查数据库连接，不自动建表或修改表结构。

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m alembic upgrade head
```

当前 PostgreSQL schema 是新的 MVP 基线，不提供 SQLite 数据迁移或双库兼容。

## 测试

完整测试：

```powershell
.\scripts\test.ps1
```

脚本会启动端口 `5433` 的独立 PostgreSQL 测试库，执行 Alembic 后运行 pytest。测试数据通过事务回滚隔离，不写入开发库。

## 项目目录

```text
longdoc-translator-agent/
├─ backend/
│  ├─ alembic/                 数据库迁移
│  ├─ app/
│  │  ├─ api/                  REST API
│  │  ├─ core/                 配置、错误、响应和日志
│  │  ├─ db/                   PostgreSQL Session
│  │  ├─ models/               SQLAlchemy ORM
│  │  ├─ schemas/              Pydantic DTO
│  │  ├─ services/             领域服务
│  │  ├─ storage/              文件路径约定
│  │  ├─ ui/                   Gradio 界面与事件处理
│  │  └─ main.py               FastAPI + Gradio 入口
│  ├─ tests/
│  ├─ alembic.ini
│  └─ requirements.txt
├─ docs/
├─ samples/
├─ scripts/
├─ storage/                    运行时文件，不提交
├─ docker-compose.yml
├─ .env.example
└─ AGENTS.md
```

## 文档

- [需求文档](docs/需求文档.md)
- [架构设计](docs/架构设计.md)
- [数据库设计](docs/数据库设计.md)
- [接口说明](docs/接口说明.md)
- [测试计划](docs/测试计划.md)
- [Gradio UI 设计](docs/前端UI设计.md)
- [文档结构与输出策略](docs/文档结构与输出策略.md)

## License

[MIT License](LICENSE)
