import gradio as gr

from app.ui import handlers

CSS = """
:root {
  --canvas: #f7f8fa;
  --surface: #ffffff;
  --ink: #172126;
  --muted: #66737b;
  --line: #dce2e5;
  --teal: #0f766e;
  --amber: #b7791f;
  --danger: #b42318;
}
.gradio-container {
  width: 100% !important;
  min-width: 0 !important;
  max-width: 1440px !important;
  margin: 0 auto !important;
  background: var(--canvas) !important;
  color: var(--ink) !important;
}
footer { display: none !important; }
.app-header {
  border-bottom: 1px solid var(--line);
  padding: 10px 2px 16px;
  margin-bottom: 14px;
}
.app-header h1 { color: var(--ink) !important; font-size: 24px !important; line-height: 1.25 !important; margin: 0 !important; }
.app-header p { color: var(--muted); margin: 4px 0 0 !important; }
.gradio-container h1, .gradio-container h2, .gradio-container h3 { color: var(--ink) !important; }
.gradio-container .prose p { color: var(--muted) !important; }
.gradio-container label,
.gradio-container .block-label,
.gradio-container .block-info,
.gradio-container .wrap label span,
.gradio-container .form label span {
  color: #243238 !important;
}
.gradio-container .block-label {
  font-weight: 700 !important;
}
.gradio-container input, .gradio-container textarea {
  background: #ffffff !important;
  color: var(--ink) !important;
  border-color: #cbd5da !important;
}
.gradio-container input[type="radio"],
.gradio-container input[type="checkbox"] {
  accent-color: var(--teal) !important;
}
.gradio-container input[type="checkbox"] {
  position: relative !important;
  width: 16px !important;
  height: 16px !important;
  border: 1px solid #8aa0a4 !important;
  border-radius: 2px !important;
}
.gradio-container input[type="checkbox"]:checked {
  background: var(--teal) !important;
  border-color: var(--teal) !important;
}
.gradio-container input[type="checkbox"]:checked::after {
  content: "" !important;
  position: absolute !important;
  left: 4px !important;
  top: 1px !important;
  width: 5px !important;
  height: 9px !important;
  border: solid #ffffff !important;
  border-width: 0 2px 2px 0 !important;
  transform: rotate(45deg) !important;
}
.gradio-container label:has(input[type="radio"]),
.gradio-container label:has(input[type="checkbox"]) {
  color: var(--ink) !important;
  background: #ffffff !important;
  border: 1px solid #cbd5da !important;
}
.gradio-container label:has(input[type="radio"]:checked),
.gradio-container label:has(input[type="checkbox"]:checked) {
  color: #0b4f49 !important;
  background: #e8f4f2 !important;
  border-color: var(--teal) !important;
  box-shadow: inset 0 0 0 1px rgba(15, 118, 110, .22) !important;
}
.gradio-container label:has(input[type="radio"]:checked) span,
.gradio-container label:has(input[type="checkbox"]:checked) span {
  color: #0b4f49 !important;
  font-weight: 700 !important;
}
.gradio-container .form { background: transparent !important; border: 0 !important; }
.login-shell {
  max-width: 460px;
  margin: 8vh auto 0;
  padding: 28px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(24, 39, 46, .08);
}
.sidebar {
  min-width: 310px;
  border-right: 1px solid var(--line);
  padding-right: 18px;
}
.main-pane { padding-left: 8px; min-width: 0; }
.status-strip { min-height: 38px; color: var(--muted); }
.job-overview {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 4px solid var(--teal);
  border-radius: 6px;
  padding: 18px 20px;
  margin-bottom: 12px;
}
.compact-table { min-width: 0 !important; overflow-x: auto !important; }
.compact-table table { font-size: 13px !important; }
.compact-table th { color: #425159 !important; font-weight: 600 !important; }
.compact-table td { vertical-align: top !important; }
button.primary { background: var(--teal) !important; }
.block-label { color: #425159 !important; font-weight: 600 !important; }
.task-list .wrap { gap: 0 !important; }
.task-list label {
  border: 0 !important;
  border-bottom: 1px solid var(--line) !important;
  border-radius: 0 !important;
  padding: 10px 8px !important;
}
.job-summary-content h2 { font-size: 22px; margin: 0; }
.job-title-row, .job-stats {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.job-title-row strong { color: var(--teal); }
.job-language { color: var(--muted); margin-top: 8px; display: flex; gap: 10px; }
.job-progress-track {
  height: 10px;
  background: #e7ecee;
  border-radius: 5px;
  overflow: hidden;
  margin: 18px 0 12px;
}
.job-progress-track span { display: block; height: 100%; background: var(--teal); }
.job-stats { color: var(--muted); font-size: 13px; }
.job-stats strong { color: var(--ink); }
.job-updated { color: var(--muted); font-size: 12px; margin-top: 12px; }
.job-risk, .job-error { margin-top: 12px; padding: 10px; border-left: 3px solid var(--amber); background: #fff8e8; }
.job-error { border-left-color: var(--danger); background: #fff1f0; }
.sidebar button { min-height: 36px !important; }@media (max-width: 600px) {
  html, body, main.app, .gradio-container,
  .gradio-container .wrap, .gradio-container .contain,
  .gradio-container .row, .gradio-container .column {
    min-width: 0 !important;
    max-width: 100% !important;
  }
  body, main.app { overflow-x: hidden !important; }
  .gradio-container { padding: 16px !important; }
  .sidebar { min-width: 0 !important; padding-right: 0 !important; border-right: 0 !important; }
  .main-pane { padding-left: 0 !important; }
  .app-header h1 { font-size: 22px !important; }
}"""

LANGUAGES = [
    ("中文", "zh"),
    ("English", "en"),
    ("日本語", "ja"),
    ("한국어", "ko"),
    ("Français", "fr"),
    ("Deutsch", "de"),
    ("Español", "es"),
    ("Português", "pt"),
    ("Русский", "ru"),
    ("العربية", "ar"),
]


def create_gradio_app() -> gr.Blocks:
    theme = gr.themes.Base(
        primary_hue="teal",
        secondary_hue="amber",
        neutral_hue="gray",
        radius_size="sm",
    ).set(
        body_background_fill="#f7f8fa",
        body_background_fill_dark="#f7f8fa",
        body_text_color="#172126",
        body_text_color_dark="#172126",
        body_text_color_subdued="#66737b",
        body_text_color_subdued_dark="#66737b",
        background_fill_primary="#ffffff",
        background_fill_primary_dark="#ffffff",
        background_fill_secondary="#f7f8fa",
        background_fill_secondary_dark="#f7f8fa",
        block_background_fill="#ffffff",
        block_background_fill_dark="#ffffff",
        block_border_color="#dce2e5",
        block_border_color_dark="#dce2e5",
        block_label_background_fill="#ffffff",
        block_label_background_fill_dark="#ffffff",
        block_label_text_color="#425159",
        block_label_text_color_dark="#425159",
        input_background_fill="#ffffff",
        input_background_fill_dark="#ffffff",
        input_background_fill_focus="#ffffff",
        input_background_fill_focus_dark="#ffffff",
        input_border_color="#cbd5da",
        input_border_color_dark="#cbd5da",
        table_text_color="#172126",
        table_text_color_dark="#172126",
        table_even_background_fill="#ffffff",
        table_even_background_fill_dark="#ffffff",
        table_odd_background_fill="#f7f8fa",
        table_odd_background_fill_dark="#f7f8fa",
        table_border_color="#dce2e5",
        table_border_color_dark="#dce2e5",
        checkbox_label_background_fill="#ffffff",
        checkbox_label_background_fill_dark="#ffffff",
        checkbox_label_text_color="#172126",
        checkbox_label_text_color_dark="#172126",
        button_secondary_background_fill="#edf1f3",
        button_secondary_background_fill_dark="#edf1f3",
        button_secondary_text_color="#243238",
        button_secondary_text_color_dark="#243238",
    )
    with gr.Blocks(
        title="LongDoc Translator Agent",
        theme=theme,
        css=CSS,
    ) as demo:
        auth_token = gr.State(value=None)
        selected_job = gr.State(value=None)

        gr.Markdown(
            "# LongDoc Translator Agent\n长文档结构化翻译工作台",
            elem_classes=["app-header"],
        )

        with gr.Column(visible=True, elem_classes=["login-shell"]) as login_panel:
            gr.Markdown("## 登录\n任务由云端 Worker 持续处理，关闭页面不会中断。")
            username = gr.Textbox(label="用户名", lines=1, max_lines=1)
            password = gr.Textbox(
                label="密码",
                type="password",
            )
            with gr.Row():
                login_button = gr.Button("登录", variant="primary")
                register_button = gr.Button("注册")
            auth_status = gr.Markdown("")

        with gr.Column(visible=False) as workspace:
            with gr.Row(equal_height=False):
                with gr.Column(scale=2, min_width=310, elem_classes=["sidebar"]):
                    user_label = gr.Markdown("")
                    logout_button = gr.Button("退出登录", size="sm")
                    job_selector = gr.Radio(
                        label="任务",
                        choices=[],
                        interactive=True,
                        elem_classes=["task-list"],
                    )
                    with gr.Row():
                        refresh_jobs = gr.Button("刷新")
                        resume_button = gr.Button("恢复")
                        cancel_button = gr.Button("取消", variant="stop")

                    gr.Markdown("### 新建翻译")
                    upload = gr.File(
                        label="PDF / Markdown / TXT",
                        file_types=[".pdf", ".md", ".txt"],
                        type="filepath",
                        height=180,
                    )
                    target_language = gr.Dropdown(
                        label="目标语言",
                        choices=LANGUAGES,
                        value="zh",
                    )
                    mode = gr.Radio(
                        label="模式",
                        choices=[("论文", "paper"), ("小说", "novel")],
                        value="paper",
                    )
                    ocr_mode = gr.Dropdown(
                        label="OCR 模式",
                        choices=[("自动", "auto"), ("关闭", "off"), ("强制", "force")],
                        value="auto",
                        visible=False,
                    )
                    require_high_risk_review = gr.Checkbox(
                        label="高风险片段暂停等待确认",
                        value=False,
                    )
                    require_chapter_review = gr.Checkbox(
                        label="章节结束暂停等待确认",
                        value=False,
                    )
                    create_button = gr.Button("开始后台翻译", variant="primary")
                    operation_status = gr.Markdown("", elem_classes=["status-strip"])

                with gr.Column(scale=7, elem_classes=["main-pane"]):
                    job_summary = gr.HTML(
                        "<p>请选择左侧任务。</p>", elem_classes=["job-overview"]
                    )
                    with gr.Tabs():
                        with gr.Tab("概览"):
                            chunks = gr.Dataframe(
                                headers=[
                                    "序号",
                                    "章节",
                                    "类型",
                                    "状态",
                                    "估算 Token",
                                    "检查",
                                ],
                                datatype=[
                                    "number",
                                    "str",
                                    "str",
                                    "str",
                                    "number",
                                    "str",
                                ],
                                interactive=False,
                                elem_classes=["compact-table"],
                            )
                        with gr.Tab("术语"):
                            terms = gr.Dataframe(
                                headers=[
                                    "原文术语",
                                    "建议译名",
                                    "确认译名",
                                    "备注",
                                    "已确认",
                                ],
                                datatype=["str", "str", "str", "str", "bool"],
                                type="array",
                                interactive=True,
                                elem_classes=["compact-table"],
                            )
                            confirm_terms_button = gr.Button(
                                "确认术语并继续", variant="primary"
                            )
                        with gr.Tab("风险"):
                            risks = gr.Dataframe(
                                headers=[
                                    "级别",
                                    "问题",
                                    "位置",
                                    "说明",
                                    "原文片段",
                                    "系统处理",
                                    "建议操作",
                                ],
                                datatype=["str"] * 7,
                                interactive=False,
                                wrap=True,
                                elem_classes=["compact-table"],
                            )
                        with gr.Tab("人工审核"):
                            reviews = gr.Dataframe(
                                headers=["类型", "位置", "状态", "备注"],
                                datatype=["str"] * 4,
                                interactive=False,
                                elem_classes=["compact-table"],
                            )
                            review_note = gr.Textbox(label="审核备注", lines=2)
                            approve_review_button = gr.Button(
                                "接受当前风险并继续", variant="primary"
                            )
                        with gr.Tab("时间线"):
                            events = gr.Dataframe(
                                headers=["时间", "阶段", "状态", "耗时", "说明"],
                                datatype=["str"] * 5,
                                interactive=False,
                                elem_classes=["compact-table"],
                            )
                        with gr.Tab("输出"):
                            gr.Markdown("任务完成后可直接下载；重新登录后仍会保留。")
                            with gr.Row():
                                bilingual_html = gr.File(
                                    label="双语 HTML", interactive=False
                                )
                                translated_html = gr.File(
                                    label="译文 HTML", interactive=False
                                )
                                package = gr.File(label="完整结果包", interactive=False)
                            with gr.Row():
                                bilingual = gr.File(
                                    label="双语 Markdown", interactive=False
                                )
                                translated = gr.File(
                                    label="译文 Markdown", interactive=False
                                )
                                report = gr.File(label="翻译报告", interactive=False)
                                source = gr.File(label="原始文件", interactive=False)

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
        auth_outputs = [
            auth_status,
            auth_token,
            user_label,
            login_panel,
            workspace,
            job_selector,
            selected_job,
        ]

        login_button.click(
            handlers.login_user,
            inputs=[username, password],
            outputs=auth_outputs,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        register_button.click(
            handlers.register_user,
            inputs=[username, password],
            outputs=auth_outputs,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        logout_button.click(
            handlers.logout_user,
            inputs=auth_token,
            outputs=auth_outputs,
        )
        refresh_jobs.click(
            handlers.list_job_choices,
            inputs=auth_token,
            outputs=[job_selector, selected_job],
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        job_selector.change(
            handlers.select_job,
            inputs=job_selector,
            outputs=selected_job,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        create_button.click(
            handlers.create_job,
            inputs=[
                auth_token,
                upload,
                mode,
                ocr_mode,
                target_language,
                require_high_risk_review,
                require_chapter_review,
            ],
            outputs=[operation_status, job_selector, selected_job],
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        cancel_button.click(
            handlers.cancel_job,
            inputs=[auth_token, selected_job],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        resume_button.click(
            handlers.resume_job,
            inputs=[auth_token, selected_job],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        confirm_terms_button.click(
            handlers.confirm_terms,
            inputs=[auth_token, selected_job, terms],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        approve_review_button.click(
            handlers.approve_pending_review,
            inputs=[auth_token, selected_job, review_note],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        upload.change(handlers.ocr_visibility, inputs=upload, outputs=ocr_mode)

        timer = gr.Timer(value=2.0, active=True)
        timer.tick(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
            show_progress="hidden",
        )

    return demo
