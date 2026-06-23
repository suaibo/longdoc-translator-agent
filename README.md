<a id="readme-top"></a>

<div align="center">

# LongDoc Translator Agent

面向论文、硕博论文和长篇文本的结构化翻译 Agent。

支持文档解析、术语确认、检查点续跑、滑动窗口记忆、双语 Markdown 导出和翻译报告生成。

[查看需求文档](./docs/需求文档.md)
·
[报告问题](https://github.com/suaibo/longdoc-translator-agent/issues)
·
[提出功能建议](https://github.com/suaibo/longdoc-translator-agent/issues)

</div>

## 目录

- [关于项目](#关于项目)
  - [项目目标](#项目目标)
  - [技术栈](#技术栈)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [安装与运行](#安装与运行)
- [使用方式](#使用方式)
- [Agent 工作流](#agent-工作流)
- [路线图](#路线图)
- [文档](#文档)
- [License](#license)
- [联系](#联系)
- [致谢](#致谢)

## 关于项目

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

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

### 项目目标

第一阶段目标是完成一个 Web 控制台：用户可以上传论文，抽取并确认术语表，启动分块翻译，查看进度和检查点，最终下载双语 Markdown、纯中文 Markdown 和翻译报告。

MVP 功能包括：

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

### 技术栈

- 后端：FastAPI
- Agent 编排：LangGraph
- 持久化：SQLite
- 文档解析：Docling
- 模型接口：OpenAI-compatible API
- 前端：React + Vite

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## 快速开始

当前仓库处于需求设计和初始实现阶段，以下为计划中的本地运行方式。

### 环境要求

- Python 3.11+
- Node.js 20+
- OpenAI-compatible LLM API Key
- 支持 PDF 解析所需的 Docling 运行环境

### 安装与运行

```bash
git clone https://github.com/suaibo/longdoc-translator-agent.git
cd longdoc-translator-agent
```

后端与前端启动命令将在实现阶段补充。

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## 使用方式

计划中的 MVP 使用流程：

1. 在 Web 控制台上传 `PDF / Markdown / TXT` 文档。
2. 系统解析文档并按章节、段落切分。
3. Agent 抽取术语表并生成建议译名。
4. 用户在术语表确认页编辑并确认译名。
5. Agent 使用确认后的术语表分块翻译全文。
6. 控制台展示 chunk 级进度、风险标记和检查点状态。
7. 翻译完成后下载双语 Markdown、纯中文 Markdown 和翻译报告。

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

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

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## 路线图

- [ ] MVP：论文翻译模式
  - [ ] PDF / Markdown / TXT 上传
  - [ ] Docling 文档解析
  - [ ] 章节与段落切分
  - [ ] 术语表抽取与人工确认
  - [ ] chunk 级翻译与检查点续跑
  - [ ] 双语 Markdown、纯中文 Markdown、报告导出
- [ ] V1：小说翻译模式
  - [ ] 人物名一致性
  - [ ] 地名和设定记忆
  - [ ] 章节级滑动窗口记忆
  - [ ] 叙事风格延续
- [ ] V2：高级审核
  - [ ] 每章翻译后人工确认
  - [ ] 风险片段人工确认
  - [ ] 术语冲突检测
  - [ ] 漏译检查
- [ ] V3：多解析器适配
  - [ ] Docling
  - [ ] Marker
  - [ ] MinerU
  - [ ] MarkItDown
- [ ] V4：更多导出格式
  - [ ] HTML
  - [ ] DOCX
  - [ ] PDF

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## 文档

- [需求文档](./docs/需求文档.md)

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## License

Distributed under the MIT License. See [LICENSE](./LICENSE) for more information.

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## 联系

Project Link: [https://github.com/suaibo/longdoc-translator-agent](https://github.com/suaibo/longdoc-translator-agent)

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>

## 致谢

- [Best-README-Template](https://github.com/othneildrew/Best-README-Template)
- [Docling](https://github.com/docling-project/docling)
- [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)

<p align="right">(<a href="#readme-top">回到顶部</a>)</p>