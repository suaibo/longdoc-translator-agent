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

仍在开发：

- DocumentIR Lite 持久化。
- DeepSeek 术语抽取与人工确认写回。
- LangGraph 节点编排、`interrupt/resume` 和 PostgreSQL checkpoint。
- 分块翻译、滑动窗口记忆、重试和指标。
- Markdown/HTML 输出、原始文件与结果资源包。

当前上传任务不会自动推进到解析与翻译阶段，相关 Worker 和 LangGraph 节点仍属于后续模块。Gradio 不会伪造尚未实现的处理结果。

## 技术栈

- 后端：Python 3.12、FastAPI、Pydantic
- 数据库：PostgreSQL 16、SQLAlchemy 2.0、Psycopg 3、Alembic
- 前端：Gradio Blocks，挂载于 FastAPI `/ui`
- Agent：LangGraph（规划中）
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
```

API Key 只能保存在本地 `.env`，不要提交到 Git。

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
