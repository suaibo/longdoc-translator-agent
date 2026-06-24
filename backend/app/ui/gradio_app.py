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
                    headers=["原文术语", "建议译名", "确认译名", "备注", "已确认"],
                    datatype=["str", "str", "str", "str", "bool"],
                    interactive=False,
                    label="术语表",
                )
                gr.Markdown("术语写回与确认将在术语服务节点实现后启用。")

            with gr.Tab("风险"):
                risks = gr.Dataframe(
                    headers=["级别", "类型", "说明", "原文片段"],
                    datatype=["str", "str", "str", "str"],
                    interactive=False,
                    label="风险项",
                )

            with gr.Tab("输出"):
                bilingual = gr.File(label="双语 Markdown", interactive=False)
                translated = gr.File(label="中文 Markdown", interactive=False)
                report = gr.File(label="翻译报告", interactive=False)

        timer = gr.Timer(value=2.0, active=True)
        dashboard_outputs = [
            job_summary,
            terms,
            chunks,
            risks,
            bilingual,
            translated,
            report,
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
            inputs=[upload, mode],
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
        timer.tick(
            handlers.refresh_dashboard,
            inputs=selected_job,
            outputs=dashboard_outputs,
            show_progress="hidden",
        )

    return demo
