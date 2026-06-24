# LongDoc Translator Agent

一个面向论文、技术报告和其他长文档的结构化翻译 Agent。

项目重点不是封装一次大模型翻译调用，而是将长文档翻译拆成可解析、可审核、可恢复、可追踪的工程流程：

```text
上传文档
-> 结构化解析与 DocumentIR
-> 结构边界优先的混合切块
-> 术语抽取
-> 人工确认术语
-> 分块翻译
-> 保存检查点
-> 生成译文与报告
```

## 项目状态

当前已经完成：

- FastAPI、SQLite、SQLAlchemy 后端基础工程
- 统一响应体、错误码和异常处理
- 核心数据库模型
- PDF、Markdown、TXT 上传
- 任务列表、任务详情、单任务限制和取消骨架
- 本地文件存储路径管理
- Docling PDF 解析适配器
- Markdown、TXT 统一转换为 `ParsedBlock[]`
- 双栏阅读顺序修正、重复页眉页脚过滤
- 表格、公式、引用、长段落和结构风险标记
- 按章节和 token 阈值生成翻译 chunk
- 小表、公式和代码原子化处理
- 大表按完整数据行分组，并保留 caption/header 合并元数据
- chunk 风险继承、幂等落库和旧 SQLite 结构增量升级

当前 Chunk Service 是“结构感知 + 句界保护 + token 预算”的规则基线，不是完整 embedding/LLM 语义切分。

后续将按模块继续实现：

- DocumentIR Lite、标题层级路径和结构资产持久化
- 结构边界优先、语义边界辅助、token 上限兜底的混合切分
- DeepSeek 术语抽取与人工确认
- 分块翻译、滑动窗口记忆和 LangGraph 检查点
- HTML 阅读输出、结果资源包、失败恢复和翻译报告
- React Web 控制台完整流程

## 当前实现边界

- Chunk Service 已作为独立领域服务实现，尚未接入 LangGraph Worker，因此上传任务不会自动推进到切块阶段。
- `ParserService` 已支持 `ocrMode=auto / off / force`，但创建任务接口和后台 Worker 尚未把该参数传入解析流程；前端接入前需要补齐这段链路。
- `CHUNK_MAX_TOKENS` 使用本地启发式 token 估算，不等同于 DeepSeek 服务端 tokenizer；接入真实 LLM 后需要用调用指标校准阈值。
- `TABLE_MAX_ROWS` 控制大表的最大行组；只有超过行数或 token 阈值的表格才会拆分。
- PDF caption 优先通过 Docling 引用关联，Markdown/TXT 使用相邻 caption 作为 fallback。引用缺失或复杂跨页表格仍保留原结果并进入风险检查。
- 当前数据库采用启动时加法迁移，为已有 SQLite 增加新列，不删除或改写旧列。进入多环境部署前应再引入 Alembic。
- 分块前的正文结构当前主要保存在内存 `ParsedBlock[]` 和 `storage/parsed/{jobId}/document.md`；可持久化 `document.ir.json`、标题路径和语义边界元数据尚未实现。
- GFM Markdown 表格只适合简单二维表格，源码中的 `|` 不保证视觉对齐；复杂表格的 HTML 渲染、原图兜底和资源包输出属于下一阶段。
- 原始 PDF 会保留，但当前没有翻译 PDF；后续优先做原 PDF + 双语批注，再考虑重排中文版 PDF。

## MVP 范围

MVP 支持：

- 上传 `PDF / Markdown / TXT`
- 使用 Docling 解析 PDF
- 按结构生成统一文档块
- 以结构边界为硬约束切分章节、段落和表格；后续加入可解释语义边界
- 使用 DeepSeek 抽取术语并等待人工确认
- 使用确认后的术语分块翻译
- 每个 chunk 完成后保存状态和检查点
- 失败后从最近完成位置继续
- 在 chunk 边界取消任务
- 导出 `bilingual.md`、`translated.md` 和 `report.md`；MVP 输出增强阶段增加 HTML、原始文件和 `result.zip`

MVP 暂不包含：

- 登录、权限和多用户隔离
- 多任务并发队列
- WebSocket / SSE
- 向量数据库、RAG 和翻译记忆库
- DOCX 和翻译 PDF 导出；HTML 阅读输出已进入 MVP 输出增强 TODO
- 完整小说翻译模式

## 技术栈

- 后端：Python、FastAPI、SQLAlchemy、SQLite、Pydantic
- Agent：LangGraph
- 文档解析：Docling、RapidOCR
- LLM：DeepSeek OpenAI-compatible API
- 前端：React、Vite、TypeScript
- 存储：本地文件系统

## 环境要求

- Python 3.11+
- Node.js 20+
- Windows PowerShell
- DeepSeek API Key
- 首次解析 PDF 时可访问 Hugging Face 以下载 Docling 模型

## 快速开始

### 1. 配置环境变量

```powershell
Copy-Item .env.example .env
```

在 `.env` 中填写 DeepSeek 配置：

```text
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=your_deepseek_key
LLM_MODEL=deepseek-v4-flash
```

API Key 只能保存在本地 `.env` 中，不要提交到 Git。

### 2. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 3. 准备 Docling 模型

首次运行 PDF 解析前下载布局和表格模型：

```powershell
.\.venv\Scripts\docling-tools.exe models download layout tableformerv2
```

Docling 默认将模型保存到用户缓存目录。模型不可用时，解析服务返回业务错误码 `50002`。

OCR 默认使用 `rapidocr-onnxruntime`，避免本机安装 PyTorch 后 RapidOCR 自动选择不兼容的推理后端。

### 4. 启动后端

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```text
GET http://127.0.0.1:8000/api/health
```

### 5. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

## 测试

运行后端测试：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests -q
```

运行静态检查（首次使用先安装 Ruff）：

```powershell
.\.venv\Scripts\python.exe -m pip install ruff
cd backend
..\.venv\Scripts\ruff.exe check app tests
```

构建前端：

```powershell
cd frontend
npm run build
```

## 项目目录

```text
longdoc-translator-agent/
├─ backend/                 FastAPI 后端
│  ├─ app/
│  │  ├─ api/              REST API 路由
│  │  ├─ core/             配置、响应、错误码和日志
│  │  ├─ db/               数据库连接与初始化
│  │  ├─ models/           SQLAlchemy ORM 模型
│  │  ├─ schemas/          Pydantic DTO、解析和 chunk 中间模型
│  │  ├─ services/         任务、解析、版面标准化和切块服务
│  │  ├─ storage/          运行时存储路径
│  │  └─ main.py           FastAPI 应用入口
│  ├─ tests/               后端测试
│  └─ requirements.txt
├─ frontend/                React + Vite 前端
├─ docs/                    需求、架构、数据库、接口和测试文档
├─ samples/                 演示文档
├─ scripts/                 本地开发脚本
└─ storage/                 上传、解析和输出文件，不提交运行时内容
```

更完整的模块规划见 [架构设计](docs/架构设计.md)。

## 文档

- [需求文档](docs/需求文档.md)
- [架构设计](docs/架构设计.md)
- [数据库设计](docs/数据库设计.md)
- [接口说明](docs/接口说明.md)
- [测试计划](docs/测试计划.md)
- [前端 UI 与交互规范](docs/前端UI设计.md)
- [文档结构、混合切分与输出策略](docs/文档结构与输出策略.md)

## License

本项目采用 [MIT License](LICENSE)。
