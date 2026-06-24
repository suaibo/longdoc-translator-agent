import gradio as gr

from app.ui import handlers

CSS = """
.gradio-container { max-width: 1180px !important; }
.app-title { margin-bottom: 0.25rem; }
.status-strip { min-height: 3rem; }
footer { display: none !important; }
"""


def create_gradio_app() -> gr.Blocks:
    with gr.Blocks(
        title="LongDoc Translator Agent",
        theme=gr.themes.Base(
            primary_hue="teal",
            secondary_hue="amber",
            neutral_hue="gray",
        ),
        css=CSS,
    ) as demo:
        selected_job = gr.State(value=None)
        gr.Markdown(
            "# LongDoc Translator Agent\n"
            "结构化长文档翻译工作台",
            elem_classes=["app-title"],
        )

        with gr.Row():
            job_selector = gr.Dropdown(
                label="当前任务",
                choices=[],
                interactive=True,
                scale=5,
            )
            refresh_jobs = gr.Button("刷新任务", variant="secondary", scale=1)
            resume_button = gr.Button("恢复任务", variant="secondary", scale=1)
            cancel_button = gr.Button("取消任务", variant="stop", scale=1)

        operation_status = gr.Markdown("", elem_classes=["status-strip"])

        with gr.Tabs():
            with gr.Tab("新建任务"):
                upload = gr.File(
                    label="文档",
                    file_types=[".pdf", ".md", ".txt"],
                    type="filepath",
                )
                mode = gr.Dropdown(
                    label="翻译模式",
                    choices=[("论文", "paper")],
                    value="paper",
                )
                ocr_mode = gr.Dropdown(
                    label="OCR 模式（仅 PDF）",
                    choices=[
                        ("自动", "auto"),
                        ("关闭", "off"),
                        ("强制", "force"),
                    ],
                    value="auto",
                    visible=False,
                )
                require_high_risk_review = gr.Checkbox(
                    label="高风险 chunk 需要人工确认",
                    value=False,
                )
                require_chapter_review = gr.Checkbox(
                    label="每章结束需要人工确认",
                    value=False,
                )
                create_button = gr.Button("创建任务", variant="primary")

            with gr.Tab("任务概览"):
                job_summary = gr.Markdown("请选择任务。")
                chunks = gr.Dataframe(
                    headers=["序号", "章节", "类型", "状态", "估算 Token", "风险"],
                    datatype=["number", "str", "str", "str", "number", "bool"],
                    interactive=False,
                    label="文档分块",
                )

            with gr.Tab("术语审核"):
                terms = gr.Dataframe(
                    headers=[
                        "术语 ID",
                        "原文术语",
                        "建议译名",
                        "确认译名",
                        "备注",
                        "已确认",
                    ],
                    datatype=["str", "str", "str", "str", "str", "bool"],
                    type="array",
                    interactive=True,
                    label="术语表",
                )
                confirm_terms_button = gr.Button("确认术语并继续", variant="primary")

            with gr.Tab("风险"):
                risks = gr.Dataframe(
                    headers=["级别", "类型", "说明", "原文片段"],
                    datatype=["str", "str", "str", "str"],
                    interactive=False,
                    label="风险项",
                )

            with gr.Tab("工作流时间线"):
                events = gr.Dataframe(
                    headers=["时间", "节点", "状态", "耗时(ms)", "说明"],
                    datatype=["str", "str", "str", "number", "str"],
                    interactive=False,
                    label="节点执行记录",
                )

            with gr.Tab("人工审核"):
                reviews = gr.Dataframe(
                    headers=["审核 ID", "类型", "对象", "状态", "处理备注"],
                    datatype=["str", "str", "str", "str", "str"],
                    interactive=False,
                    label="审核请求",
                )
                review_note = gr.Textbox(label="审核备注", lines=2)
                approve_review_button = gr.Button(
                    "批准当前待审核项并继续",
                    variant="primary",
                )

            with gr.Tab("输出"):
                bilingual = gr.File(label="双语 Markdown", interactive=False)
                translated = gr.File(label="中文 Markdown", interactive=False)
                report = gr.File(label="翻译报告", interactive=False)
                bilingual_html = gr.File(label="双语 HTML", interactive=False)
                translated_html = gr.File(label="中文 HTML", interactive=False)
                package = gr.File(label="结果资源包", interactive=False)
                source = gr.File(label="原始文件", interactive=False)

        timer = gr.Timer(value=2.0, active=True)
        dashboard_outputs = [
            job_summary,
            terms,
            chunks,
            risks,
            events,
            reviews,
            bilingual,
            translated,
            report,
            bilingual_html,
            translated_html,
            package,
            source,
        ]

        demo.load(
            handlers.list_job_choices,
            outputs=[job_selector, selected_job],
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        refresh_jobs.click(
            handlers.list_job_choices,
            outputs=[job_selector, selected_job],
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        job_selector.change(
            handlers.select_job,
            inputs=job_selector,
            outputs=selected_job,
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        create_button.click(
            handlers.create_job,
            inputs=[
                upload,
                mode,
                ocr_mode,
                require_high_risk_review,
                require_chapter_review,
            ],
            outputs=[operation_status, job_selector, selected_job],
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        cancel_button.click(
            handlers.cancel_job,
            inputs=selected_job,
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        resume_button.click(
            handlers.resume_job,
            inputs=selected_job,
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        confirm_terms_button.click(
            handlers.confirm_terms,
            inputs=[selected_job, terms],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        approve_review_button.click(
            handlers.approve_pending_review,
            inputs=[selected_job, review_note],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
        )
        upload.change(
            handlers.ocr_visibility,
            inputs=upload,
            outputs=ocr_mode,
        )
        timer.tick(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
            show_progress="hidden",
        )

    return demo
