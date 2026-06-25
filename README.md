# LongDoc Translator Agent

面向论文、技术报告和长篇文本的结构化翻译 Agent。系统不是一次 LLM 调用的封装，而是一个可分支、可暂停、可恢复、可追踪的 LangGraph 工作流。

```text
登录 -> 上传文档 -> 后台 Worker 持续运行
-> 结构化解析与版面修正
-> DeepSeek 辅助疑似语义边界判断
-> 术语人工确认
-> 分块翻译、质量检查与上下文记忆
-> 检查点恢复
-> Markdown / HTML / 原文件 / 结果包
```

用户可以关闭页面或退出登录，云端 Worker 仍会继续处理；稍后重新登录即可查看进度并下载结果。

## 当前能力

- 简化账号系统、30 天会话、任务所有权和接口隔离。
- PostgreSQL 16、SQLAlchemy 2.0、Psycopg 3、Alembic。
- PostgreSQL 租约队列、独立 Worker、每用户最多 5 个并发任务。
- 本地开发存储与 S3 兼容对象存储，可跨 Web/Worker 重启恢复文件。
- PDF、Markdown、TXT；Docling、RapidOCR、DocumentIR Lite。
- 双栏阅读顺序修正、页眉页脚过滤、caption 关联和 OCR 风险。
- 表格原子性、大表按完整行分组、公式和引用结构保护。
- 结构边界优先、DeepSeek 疑似边界判断、token 上限兜底。
- 自动检测源语言；支持中、英、日、韩、法、德、西、葡、俄、阿十种目标语言。
- LangGraph 条件边、有限重试、规则降级、chunk 回环和人工 `interrupt/resume`。
- 术语确认、滑动窗口摘要、质量检查、有限修订和用户可读风险。
- Gradio 任务工作台：历史任务、队列位置、进度、ETA、术语、风险、时间线和下载。
- 双语/译文 Markdown、HTML、翻译报告、原始文件、manifest 和 `result.zip`。

未配置 `LLM_API_KEY` 时，真实 LLM 节点会明确失败，不使用 mock 结果冒充翻译。

## 技术栈

- 后端：Python、FastAPI、Pydantic
- 数据库：PostgreSQL 16、SQLAlchemy 2.0、Psycopg 3、Alembic
- Agent：LangGraph、PostgreSQL checkpointer
- 前端：Gradio Blocks，挂载在 `/ui`
- 解析：Docling、RapidOCR
- LLM：DeepSeek OpenAI-compatible API
- 文件：本地开发目录或 S3 兼容对象存储

## 快速开始

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\scripts\start.ps1
```

必须在 `.env` 中配置：

```text
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_deepseek_key
LLM_MODEL=deepseek-v4-flash
```

云服务器推荐配置：

```text
WORKER_ENABLED=False
WORKER_MAX_CONCURRENCY=5
USER_MAX_CONCURRENT_JOBS=5
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://your-s3-compatible-endpoint
S3_BUCKET=longdoc-translator
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

生产环境分别启动 Web 与 Worker：

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

另一个进程：

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m app.worker
```

访问：

- 工作台：<http://127.0.0.1:8000/ui>
- OpenAPI：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 测试

```powershell
.\scripts\test.ps1
```

或直接运行：

```powershell
docker compose --profile test up -d test-db
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

当前测试覆盖账号隔离、任务队列、LangGraph 分支和回环、DeepSeek JSON 校验、解析/切分、人工中断、恢复与输出。

## 项目目录

```text
backend/app/
  agent/       LangGraph 状态、节点、条件边和子图
  api/         认证、任务、术语、审核与输出接口
  models/      PostgreSQL ORM
  services/    解析、切分、翻译、队列、风险和存储服务
  storage/     本地路径与 S3 兼容对象存储
  ui/          Gradio 工作台
backend/alembic/  数据库迁移
backend/tests/    单元与 PostgreSQL 集成测试
docs/             需求、架构、接口、数据库、UI 和测试文档
```

## 文档

- [需求文档](docs/需求文档.md)
- [架构设计](docs/架构设计.md)
- [数据库设计](docs/数据库设计.md)
- [接口说明](docs/接口说明.md)
- [测试计划](docs/测试计划.md)
- [Gradio UI 设计](docs/前端UI设计.md)
- [文档结构与输出策略](docs/文档结构与输出策略.md)
- [最新实施计划](docs/实施计划.md)

## 后续方向

翻译/双语批注 PDF、图片文字翻译与导出、预翻译和风格 Prompt、用户选择模型、在线编辑与版本历史、SSE/WebSocket 实时推送。

## License

[MIT License](LICENSE)
