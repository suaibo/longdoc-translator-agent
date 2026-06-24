# LongDoc Translator Agent Gradio UI 设计

版本：v0.4
状态：MVP 实现规范
前端：Gradio Blocks，挂载于 FastAPI `/ui`

## 1. 定位

Gradio 是正式 MVP 前端，不是临时静态演示。它负责让用户完成：

```text
上传文档
-> 选择任务
-> 查看状态与 chunk
-> 审核术语
-> 查看翻译进度和风险
-> 恢复或取消
-> 下载结果
```

FastAPI REST API 继续保留，为测试、后续客户端和外部集成提供稳定边界。Gradio 事件处理器直接复用 Service，每个事件创建并关闭独立数据库 Session，不通过内部 HTTP 绕行。

## 2. 当前界面

入口：`http://127.0.0.1:8000/ui`

顶部：

- 当前任务下拉框
- 刷新任务
- 取消任务
- 操作反馈

工作区标签：

- **新建任务**：上传 PDF/Markdown/TXT，选择论文模式。
- **任务概览**：状态、阶段、进度和 chunk 表。
- **术语审核**：术语表；写回能力在 TermService 完成后启用。
- **风险**：风险级别、类型、说明和原文片段。
- **输出**：双语 Markdown、中文 Markdown 和报告下载。

当前真实可用能力是上传、任务查询、轮询、取消和已有数据展示。未实现的 Agent 节点不使用伪数据模拟成功。

## 3. 状态与数据

- `gr.State` 只保存当前 `job_id`。
- PostgreSQL 是任务、术语、chunk 和风险的唯一事实来源。
- 页面加载与“刷新任务”同时更新下拉框和 `job_id`，随后刷新工作台。
- `gr.Timer` 每 2 秒刷新当前任务。
- 浏览器刷新后重新查询任务，不依赖前端内存恢复业务状态。
- 输出文件只有真实存在时才向 `gr.File` 返回路径。

## 4. 上传边界

FastAPI 使用 `UploadFile`，Gradio 使用临时文件路径。二者统一进入 `JobService`：

```text
create_job(UploadFile)
create_job_from_path(Path, original_filename)
```

共同执行扩展名、大小、模式、单活动任务和存储路径校验。数据库部分唯一索引负责并发兜底。

后续加入 OCR 控件时：

- 仅 PDF 显示 `auto/off/force`。
- 默认 `auto`。
- 参数写入任务创建命令并传给 ParserService。

## 5. 交互规则

- 所有按钮必须调用真实后端能力。
- 操作失败保留当前数据并显示明确错误。
- 取消只对活动状态开放，重复取消由业务错误提示。
- 状态、风险和进度不能只依赖颜色表达。
- 表格使用 Dataframe 展示；复杂论文表格的最终阅读采用 HTML/原图兜底，不直接把 pipe 源码作为视觉成品。
- 公式最终由 HTML 输出使用 KaTeX/MathJax；渲染失败时保留 LaTeX 和原始证据。

## 6. 响应式要求

- 默认桌面宽度控制在约 1180px。
- 390px 移动端允许标签折叠到更多菜单。
- 顶部操作在窄屏纵向排列。
- 文件名和任务 ID 可截断，但任务概览必须展示完整 ID。
- Dataframe 可横向滚动，不压缩到不可读。

## 7. 模块结构

```text
backend/app/ui/
├─ __init__.py
├─ gradio_app.py    Blocks、组件和事件链
└─ handlers.py      Session 生命周期与 Service 调用
```

当事件处理继续增长时，按 `jobs/terms/translation/outputs` 拆分 handler，不把业务逻辑搬进 UI。

## 8. 后续 TODO

- OCR 模式字段。
- TermService、可编辑术语 Dataframe 和确认按钮。
- resume 接口与恢复按钮。
- 后台 Worker 和 LangGraph 进度联动。
- chunk 原文/译文详情。
- HTML 阅读输出和原始 PDF 下载。
- 输出资源包。
- 风险片段人工确认。

## 9. 验收

- `/ui` 可正常加载，控制台无错误。
- 上传后 PostgreSQL 中创建任务并出现在下拉框。
- 刷新任务会同步当前 `job_id` 和工作台。
- 定时轮询读取真实状态。
- 取消后状态变为 `CANCELLED`。
- 1280px 和 390px 下无不可用控件或文本重叠。
- REST API `/api/*` 与 Gradio 同时可用。
