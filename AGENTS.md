# LongDoc Translator Agent Context

> 这个文件用于给后续单开线程的 AI / Codex 提供项目上下文。  
> 当用户在 LongDoc Translator Agent 项目里询问实现、架构、接口、Agent 工作流、数据库、前后端联调或测试时，优先参考本文档和 `docs/` 下的设计文档。

---

## 1. 当前权威文档

后续回答和实现时，优先参考以下文档：

- `README.md`
- `docs/需求文档.md`
- `docs/架构设计.md`
- `docs/数据库设计.md`
- `docs/接口说明.md`
- `docs/测试计划.md`
- `docs/前端UI设计.md`
- `docs/文档结构与输出策略.md`

如果文档之间冲突，优先级如下：

```text
用户最新明确指令 > docs/需求文档.md > docs/架构设计.md > docs/文档结构与输出策略.md > docs/接口说明.md > docs/前端UI设计.md > docs/数据库设计.md > docs/测试计划.md > README.md
```

原则：如果修改了架构、接口、数据表或 MVP 范围，需要同步更新对应文档，不要只改代码。

---

## 2. 项目定位

LongDoc Translator Agent 是一个面向长文档的结构化翻译 Agent。

MVP 目标：

> 完整跑通“论文翻译模式”：上传文档 -> 结构化解析 -> DocumentIR/章节结构 -> 混合切块 -> 抽取术语 -> 人工确认术语 -> 分块翻译 -> 保存检查点 -> 导出可编辑 Markdown、可读 HTML、原始文件和翻译报告。

它不是：

- 普通聊天机器人
- 简单文本翻译网页
- 只调用一次大模型的 Demo
- 专门的 OCR 系统
- 完整 PDF 排版还原工具
- 多用户 SaaS 平台
- 文档协作平台
- 翻译记忆库商业系统

MVP 的核心竞争力是：

```text
长文档翻译流程的工程化：结构化解析、DocumentIR、可解释混合切分、术语确认、滑动窗口记忆、检查点恢复、复杂结构渲染和风险报告。
```

判断一个功能是否应该进入 MVP，先问：

```text
它是否直接帮助演示长文档 Agent 的完整工作流和工程深度？
```

如果答案是否定的，默认后置。

---

## 3. 技术栈

后端：

- Python
- FastAPI
- PostgreSQL 16
- SQLAlchemy 2.0
- Psycopg 3
- Alembic
- Pydantic

Agent：

- LangGraph
- OpenAI-compatible LLM API
- checkpoint / interrupt / memory 机制

文档解析：

- Docling
- MVP 支持 `PDF / Markdown / TXT`

前端：

- Gradio Blocks
- 挂载到 FastAPI `/ui`
- Gradio handler 复用 Service，不通过内部 HTTP 调用自身 API

运行与存储：

- 本地文件系统存储上传文件、解析结果和输出文件
- PostgreSQL 保存任务、chunk、术语、检查点、指标和风险项
- Docker Compose 提供默认开发库和独立测试库

---

## 4. MVP 功能边界

MVP 必做：

- 上传 `PDF / Markdown / TXT`
- 创建翻译任务
- 查询任务列表和任务详情
- Docling 解析 PDF，输出 ParsedBlock、调试 Markdown，并逐步构建 DocumentIR Lite
- Markdown / TXT 进入统一切分流程
- 结构边界优先、语义边界辅助、token 上限兜底地切分 chunk
- 标记表格、公式、引用、疑似 OCR 异常等风险片段
- Agent 抽取术语表和建议译名
- 人工编辑并确认术语表
- 术语确认后继续翻译
- chunk 级翻译进度
- 每个 chunk 完成后保存数据库状态和检查点
- 失败后可从最近完成 chunk 恢复
- 可取消任务
- 基础导出：`bilingual.md`、`translated.md`、`report.md`
- 输出增强：`bilingual.html`、`translated.html`、原始文件和 `result.zip`
- Web 控制台完整演示上传、术语确认、进度和下载

MVP 暂不做：

- 登录 / 注册 / 权限
- 多用户隔离
- 多任务并发队列
- WebSocket / SSE 实时推送
- DOCX 导出
- 翻译 PDF 导出（原始 PDF 保留与下载属于 MVP 输出增强）
- 在线编辑译文
- 翻译记忆库 TM
- 向量数据库
- RAG 问答
- 支付或额度系统
- 云存储
- 小说模式完整实现

V1 可扩展：

- 小说翻译模式
- 人名、地名、设定记忆
- 章节级摘要记忆
- 风格一致性检查
- 每章人工确认
- 风险片段人工确认
- 可插拔解析器：Marker / MinerU / MarkItDown
- DOCX / 双语批注 PDF / 重排中文版 PDF
- SSE 进度推送

---

## 5. OCR 决策

Docling 内置 OCR 能力，MVP 可以接入，但不要把 OCR 做成独立主线系统。

MVP 推荐策略：

```text
PDF 解析统一走 Docling。
OCR 作为 ParserService 的解析选项，而不是单独的 OCRService。
```

建议参数：

```text
ocrMode: auto | off | force
```

含义：

- `auto`：默认模式。优先使用 PDF 内置文本；Docling 判断需要时启用 OCR。
- `off`：关闭 OCR，适合文字型 PDF，速度更快。
- `force`：强制 OCR，适合扫描版 PDF，但耗时更长。

实现建议：

- 后端配置 `ocrEngine`，默认使用 Docling 默认的 EasyOCR。
- 前端 MVP 可以只暴露 `ocrMode`，不要让用户选择具体 OCR 引擎。
- `ocrEngine` 可以通过环境变量或后端配置切换，后续再扩展为 Tesseract / RapidOCR 等。
- OCR 失败时任务进入 `FAILED`，保留错误信息。
- OCR 质量不稳定的片段写入 `risk_item`，在 `report.md` 里提示人工检查。

重要边界：

```text
MVP 不承诺完美还原论文版式，也不承诺 OCR 结果 100% 正确。
MVP 要展示的是“长文档 Agent 流程工程能力”，不是专业 OCR 产品能力。
```

---

## 6. 推荐目录模块

建议按下面结构开工。具体文件名可以根据框架习惯微调，但模块职责不要混在一起。

```text
longdoc-translator-agent/
  backend/
    app/
      main.py
      api/
        routes_health.py
        routes_jobs.py
        routes_terms.py
        routes_chunks.py
        routes_outputs.py
      core/
        config.py
        errors.py
        response.py
        logging.py
      db/
        session.py
      models/
        translation_job.py
        document_chunk.py
        term_entry.py
        agent_checkpoint.py
        translation_metric.py
        risk_item.py
      schemas/
        common.py
        job.py
        term.py
        chunk.py
        output.py
      services/
        job_service.py
        parser_service.py
        chunk_service.py
        term_service.py
        translation_service.py
        checkpoint_service.py
        output_service.py
        metric_service.py
        risk_service.py
      agent/
        state.py
        graph.py
        nodes.py
        prompts.py
      ui/
        gradio_app.py
        handlers.py
      storage/
        paths.py
    alembic/
    tests/
      unit/
      integration/
  docs/
  samples/
  storage/
  docker-compose.yml
```

`storage/` 是运行时目录，原则上不提交真实上传文件、数据库文件和输出文件。

---

## 7. 后端模块职责

`api/`：

- 只处理 HTTP 参数、响应、状态码和调用 service。
- 不直接写复杂业务逻辑。

`core/`：

- 配置读取
- 统一响应体
- 统一异常
- 日志
- 错误码

`db/`：

- PostgreSQL 连接
- session 管理
- 连接健康检查
- 表结构只通过 Alembic 迁移

`models/`：

- 数据库 ORM 模型
- 表字段和约束以 `docs/数据库设计.md` 为准

`schemas/`：

- Pydantic 请求 / 响应 DTO
- API 字段以 `docs/接口说明.md` 为准

`services/`：

- 领域服务，不依赖前端
- 文件存储、任务状态、解析、切分、术语、翻译、输出、指标、风险都在这里分离

`agent/`：

- LangGraph state
- 节点函数
- graph 编排
- prompt 模板
- interrupt / resume 逻辑

---

## 8. Gradio 模块职责

- `gradio_app.py`：构建上传、任务、术语、风险和输出工作区。
- `handlers.py`：管理事件级 Session，并调用 Service。
- `gr.State` 只保存当前 `job_id`，业务状态始终重新查询 PostgreSQL。
- 使用 `gr.Timer` 轮询活动任务。
- FastAPI REST API 保持独立可用，不把领域逻辑写入 Gradio 回调。

---

## 9. Agent 工作流

MVP LangGraph 节点：

```text
parse_document
  -> split_sections
  -> extract_terms
  -> interrupt_for_term_review
  -> translate_chunk
  -> summarize_chunk_context
  -> mark_risks
  -> generate_outputs
  -> generate_report
```

任务状态：

```text
UPLOADED
PARSED
WAITING_TERM_REVIEW
TRANSLATING
COMPLETED
FAILED
CANCELLED
```

核心规则：

1. 上传任务后，后台 worker 自动执行解析、切分、术语抽取。
2. 抽取术语后进入 `WAITING_TERM_REVIEW`。
3. 用户确认术语后，任务进入 `TRANSLATING`。
4. 每个 chunk 翻译完成后写入 `document_chunk`、`agent_checkpoint` 和必要指标。
5. 失败时任务进入 `FAILED`，已完成 chunk 不丢失。
6. `resume` 从最近完成的 chunk 继续。
7. `cancel` 设置任务取消标记，worker 在 chunk 边界停止。

---

## 10. API 范围

统一响应体：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

核心接口：

```text
GET  /api/health
POST /api/jobs
GET  /api/jobs
GET  /api/jobs/{jobId}
GET  /api/jobs/{jobId}/terms
PUT  /api/jobs/{jobId}/terms
GET  /api/jobs/{jobId}/chunks
GET  /api/jobs/{jobId}/outputs/{type}
POST /api/jobs/{jobId}/resume
POST /api/jobs/{jobId}/cancel
```

错误码以 `docs/接口说明.md` 为准。

状态不允许的操作必须返回业务冲突错误，不要静默忽略。

---

## 11. 数据库核心表

MVP 核心表：

- `translation_job`
- `document_chunk`
- `term_entry`
- `agent_checkpoint`
- `translation_metric`
- `risk_item`

关键约束：

- `translation_job.job_id` 主键
- `document_chunk(job_id, chunk_index)` 唯一
- `term_entry(job_id, source_term)` 唯一
- chunk、term、risk 都必须关联 `translation_job`

数据库设计以 `docs/数据库设计.md` 为准。

不要提前加入：

- 用户表
- 权限表
- 组织表
- 支付表
- 多租户字段

---

## 12. 存储目录约定

运行时目录：

```text
storage/uploads/{jobId}/original.ext
storage/parsed/{jobId}/document.md
storage/parsed/{jobId}/document.ir.json        # 输出增强前置，尚未实现
storage/parsed/{jobId}/assets/
storage/outputs/{jobId}/bilingual.md
storage/outputs/{jobId}/translated.md
storage/outputs/{jobId}/report.md
storage/outputs/{jobId}/bilingual.html         # 输出增强
storage/outputs/{jobId}/translated.html        # 输出增强
storage/outputs/{jobId}/manifest.json          # 输出增强
storage/outputs/{jobId}/result.zip             # 输出增强
```

建议：

- 上传原文件保留原始文件名和安全后的存储文件名。
- 数据库保存文件路径和原始文件名。
- 输出文件统一由 `OutputService` 生成，复杂结构交给 RenderService 按 GFM / HTML / image fallback 渲染。
- 不要把真实用户上传文件提交到 Git。

---

## 13. 推荐开发顺序

建议按以下顺序实现：

1. 初始化 FastAPI / Gradio 基础工程。
2. 配置 `.env.example`、`.gitignore`、运行脚本。
3. 实现统一响应体、错误码、异常处理。
4. 建 PostgreSQL 模型与 Alembic 初始迁移。
5. 实现任务创建、文件上传、任务列表、任务详情。
6. 先实现 Markdown / TXT 解析，跑通最小流程。
7. 实现 chunk 规则基线和风险标记。
8. 实现标题栈、sectionPath、DocumentIR Lite 和结构资产。
9. 实现 target/soft/hard 预算、可解释边界和可降级语义评分。
10. 接入术语抽取，先允许 mock LLM，再接真实 OpenAI-compatible API。
11. 实现术语确认接口和前端页面。
12. 实现翻译 worker，先 mock 翻译，再接真实 LLM。
13. 实现 chunk 级检查点、失败状态、resume 和 cancel。
14. 实现基础 Markdown 输出。
15. 实现表格/公式分级渲染、HTML、原始文件下载和 result.zip。
16. 接入 Docling PDF 解析和 OCR 模式。
17. 补测试、README、演示样例和截图。

原则：

```text
先跑通 Markdown 样例完整闭环，再增强 PDF / OCR / Docling。
```

这样可以避免一开始被 PDF 解析环境卡住，导致 Agent 主流程没有进展。

---

## 14. LLM 与 Prompt 规则

LLM 调用必须通过统一服务封装，不要在各个节点里散落调用逻辑。

建议封装：

- `extract_terms(text) -> list[TermEntry]`
- `translate_chunk(chunk, terms, section_summary, previous_summary) -> translated_text`
- `summarize_chunk(original, translated) -> summary`

环境变量建议：

```text
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

开发规则：

- 没有 API Key 时允许使用 mock LLM 跑通流程。
- 真实 LLM 失败时记录错误和重试次数。
- Prompt 模板集中放在 `backend/app/agent/prompts.py`。
- 术语抽取结果必须做 JSON 解析和字段校验。
- 不要把 API Key 写进代码、README 示例输出或测试文件。

---

## 15. 测试重点

单元测试：

- Markdown / TXT 解析
- 章节与段落切分
- 表格风险识别
- 术语表 JSON 解析和校验
- 输出文件生成
- 任务状态流转

集成测试：

- 上传 Markdown 论文片段，完整跑到术语确认
- 确认术语后完成翻译
- 翻译失败后保留已完成 chunk
- `resume` 从最近 checkpoint 继续
- `cancel` 后任务停止
- 输出文件可下载

验收演示：

- `sample-paper.md` 完整演示
- `sample-long.txt` 完整演示
- PDF 通过 Docling 解析后进入同一工作流
- 表格被保留并写入风险报告

测试计划以 `docs/测试计划.md` 为准。

---

## 16. 实现时的固定判断框架

当用户问某个技术点、取舍或实现方案时，例如：

- “OCR 要怎么接？”
- “LangGraph checkpoint 怎么做？”
- “要不要用 SSE？”
- “任务队列怎么设计？”
- “Docling 解析失败怎么办？”
- “前端状态怎么管理？”

请按下面结构回答：

1. 这个技术 / 方案是什么
2. 它解决什么问题
3. 在本项目里放在哪个模块
4. MVP 现在需不需要
5. 如果需要，给出最小实现方式
6. 如果不需要，说明什么时候再引入
7. 不要直接上复杂方案

判断标准：

```text
能不能帮助本周演示完整长文档 Agent 工作流？
能不能体现结构化解析、HITL、滑动窗口记忆、检查点恢复这些 Agent 工程能力？
能不能降低前后端联调和排错成本？
```

如果答案是否定的，MVP 阶段先不引入。

---

## 17. 当前最重要的边界

当前项目最重要的是：

> 快速做出一个可演示、可写进简历、能体现 Agent 工程能力的长文档翻译系统。

不要为了技术完整性提前加入：

- 登录权限
- 多用户系统
- 多任务并发
- 云部署架构
- 复杂 UI 设计系统
- 向量数据库
- RAG 问答
- 翻译记忆库
- 商业级 OCR 调参
- 完整小说模式

先让 MVP 跑起来，再逐步增强深度。

---

## 18. 文档结构、切分与输出固定决策

后续实现必须遵守 `docs/文档结构与输出策略.md`：

### 18.1 当前与目标能力

- 当前 Chunk Service 是结构感知、句界保护、单一 token 阈值的规则基线。
- 不得把当前实现宣传为完整语义切分。
- 目标算法是“结构边界优先、语义边界辅助、token 上限兜底”。
- 语义评分服务不可用时必须回退规则基线，不让主流程失败。

### 18.2 分块前结构

- 当前正文 block 暂存在 `ParsedBlock[]`，并渲染到 `document.md`。
- 目标增加版本化 `document.ir.json`，保存标题树、sectionPath、TableIR、FormulaIR、FigureIR 和资产引用。
- Markdown 是渲染结果，不是复杂论文结构的唯一真相。

### 18.3 表格和公式

- 简单可信表格使用 GFM。
- 复杂可信表格使用 HTML table。
- 低置信度表格使用原始截图、可用 CSV/JSON 和风险说明。
- 不能为了视觉整齐猜测性重建表格。
- 公式优先保存 LaTeX、编号和原始截图兜底，不让翻译模型改写公式结构。

### 18.4 输出与 PDF

- Markdown 用于可编辑交换。
- HTML 用于用户直接阅读。
- result.zip 携带 HTML、Markdown、原始文件和所有资产。
- 原始 PDF 必须完整保留，但不能称为翻译 PDF。
- V1 优先做双语批注 PDF，V2 再做重排中文版 PDF。
- HTML 必须转义不可信文本并使用标签白名单；ZIP/manifest 路径必须防止路径穿越。

### 18.5 实现顺序

1. 标题栈和 sectionPath。
2. DocumentIR Lite 与结构资产。
3. target/soft/hard token 预算和边界原因。
4. 本地语义相似度与可插拔 embedding。
5. TableIR/FormulaIR/FigureIR 渲染。
6. HTML、manifest、原始文件下载和 result.zip。
7. 双语批注 PDF。
