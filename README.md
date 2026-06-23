# LongDoc Translator Agent

面向论文、硕博论文和长篇文本的结构化翻译 Agent，支持文档解析、术语确认、检查点续跑、滑动窗口记忆、双语 Markdown 导出和翻译报告生成。

## 项目简介

LongDoc Translator Agent 不是简单的“调用大模型翻译一段文本”，而是一个面向长文档翻译场景的 Agent 工作流项目。

MVP 阶段优先支持 **论文翻译模式**，后续扩展 **长篇小说翻译模式**。项目重点展示长文档处理中常见的工程问题：

- 文档结构解析
- 章节与段落切分
- 术语一致性维护
- Human-in-the-Loop 术语确认
- 长文本上下文连续性
- 检查点持久化与失败续跑
- 表格 / 公式等高风险片段标记
- 双语译文与翻译报告导出

## MVP 功能

- 上传 `PDF / Markdown / TXT` 文档。
- 使用 Docling 将文档解析为结构化 Markdown。
- 按“章节 + 段落”切分长文档。
- 翻译前抽取术语表。
- 暂停等待用户确认或编辑术语译名。
- 使用确认后的术语表进行分块翻译。
- 使用章节摘要和前一块摘要实现滑动窗口记忆。
- 使用 SQLite 保存任务状态、分块、术语和检查点。
- 支持失败后从最近完成的 chunk 继续翻译。
- 导出双语 Markdown、纯中文 Markdown 和翻译报告。

## 技术栈

- 后端：FastAPI
- Agent 编排：LangGraph
- 持久化：SQLite
- 文档解析：Docling
- 模型接口：OpenAI-compatible API
- 前端：React + Vite

## Agent 工作流

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

第一版 Human-in-the-Loop 节点是 **术语表确认**。Agent 会先抽取候选术语和建议译名，等待用户确认后再继续批量翻译。

## 项目模式

### 论文翻译模式

MVP 优先实现的模式，面向论文、硕博论文、技术报告等结构化文档。

重点能力：

- 保留章节结构
- 维护术语一致性
- 保留并标记表格风险
- 输出双语对照译文
- 生成翻译进度与风险报告

### 小说翻译模式

后续版本规划。

重点能力：

- 人物名一致性
- 地名和设定记忆
- 叙事风格延续
- 章节级滑动窗口记忆
- 长任务检查点续跑

## 文档

- [需求文档](./需求文档.md)

## 当前状态

项目处于需求设计和初始实现阶段。

第一阶段目标是完成一个 Web 控制台：用户可以上传论文，抽取并确认术语表，启动分块翻译，查看进度和检查点，最终下载双语 Markdown、纯中文 Markdown 和翻译报告。

## License

MIT
