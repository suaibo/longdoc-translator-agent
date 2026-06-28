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
  max-width: 1440px !important;
  margin: 0 auto !important;
  background: var(--canvas) !important;
  color: var(--ink) !important;
}
footer { display: none !important; }
.gradio-container,
.gradio-container .main,
.gradio-container .app,
.gradio-container .contain,
.gradio-container .block,
.gradio-container .form,
.gradio-container .panel,
.gradio-container .wrap,
.gradio-container .input-container,
.gradio-container .tabs,
.gradio-container .tabitem,
.gradio-container .file-preview,
.gradio-container .upload-container,
.gradio-container .table-wrap,
.gradio-container [role="grid"],
.gradio-container [role="row"],
.gradio-container [role="gridcell"],
.gradio-container [role="columnheader"] {
  background-color: var(--surface) !important;
  color: var(--ink) !important;
  border-color: var(--line) !important;
  box-shadow: none !important;
}
.gradio-container > .main,
.gradio-container .main > .wrap {
  background-color: var(--canvas) !important;
}
.app-header { border-bottom: 1px solid var(--line); padding-bottom: 14px; }
.app-header h1 { color: var(--ink) !important; font-size: 24px !important; margin: 0 !important; }
.app-header p,
.gradio-container .prose,
.gradio-container .markdown,
.gradio-container .md,
.gradio-container .prose p,
.gradio-container .markdown p {
  color: var(--ink) !important;
  opacity: 1 !important;
}
.app-header p,
.gradio-container .prose p,
.gradio-container .markdown p,
.gradio-container .md p,
.gradio-container small,
.gradio-container .secondary-text {
  color: var(--muted) !important;
  opacity: 1 !important;
}
.gradio-container .prose h1,
.gradio-container .prose h2,
.gradio-container .prose h3,
.gradio-container .md h1,
.gradio-container .md h2,
.gradio-container .md h3,
.gradio-container .markdown h1,
.gradio-container .markdown h2,
.gradio-container .markdown h3 {
  color: var(--ink) !important;
  opacity: 1 !important;
}
.gradio-container label,
.gradio-container legend,
.gradio-container fieldset,
.gradio-container strong,
.gradio-container .block-label,
.gradio-container .block-info,
.gradio-container .label-wrap,
.gradio-container .label-wrap span,
.gradio-container span.svelte-g2oxp3,
.gradio-container .wrap label span,
.gradio-container .form label span {
  color: #243238 !important;
  opacity: 1 !important;
}
.gradio-container .block-label { font-weight: 700 !important; }
.gradio-container input,
.gradio-container textarea,
.gradio-container select,
.gradio-container [role="combobox"] {
  background: #ffffff !important;
  color: var(--ink) !important;
  border-color: #cbd5da !important;
  box-shadow: none !important;
}
.gradio-container input::placeholder,
.gradio-container textarea::placeholder {
  color: #6b7280 !important;
  opacity: 1 !important;
}
.gradio-container option {
  background: #ffffff !important;
  color: var(--ink) !important;
}
.gradio-container input[type="radio"],
.gradio-container input[type="checkbox"] { accent-color: var(--teal) !important; }
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
}
.gradio-container [role="tab"],
.gradio-container button[role="tab"] {
  background: #ffffff !important;
  color: #425159 !important;
  border-color: var(--line) !important;
}
.gradio-container [role="tab"][aria-selected="true"],
.gradio-container button[role="tab"][aria-selected="true"],
.gradio-container .selected {
  color: #0b4f49 !important;
  border-color: var(--teal) !important;
}
.gradio-container table,
.gradio-container thead,
.gradio-container tbody,
.gradio-container tr,
.gradio-container th,
.gradio-container td {
  background: #ffffff !important;
  color: var(--ink) !important;
  border-color: var(--line) !important;
}
.gradio-container th,
.gradio-container [role="columnheader"] {
  color: #425159 !important;
  font-weight: 700 !important;
}
.gradio-container td,
.gradio-container [role="gridcell"] {
  color: var(--ink) !important;
}
.gradio-container button.primary,
.gradio-container button.secondary,
.gradio-container button.stop,
.gradio-container button.lg {
  color: #ffffff !important;
  border-color: transparent !important;
  font-weight: 700 !important;
}
.gradio-container button.primary span,
.gradio-container button.secondary span,
.gradio-container button.stop span,
.gradio-container button.lg span {
  color: inherit !important;
}
.gradio-container button.primary {
  background: var(--teal) !important;
  color: #ffffff !important;
}
.gradio-container button.secondary,
.gradio-container button.lg:not(.primary):not(.stop) {
  background: #556170 !important;
  color: #ffffff !important;
}
.gradio-container button.stop {
  background: var(--danger) !important;
  color: #ffffff !important;
}
.gradio-container button.boundedheight {
  background: #ffffff !important;
  color: var(--ink) !important;
  border: 1px dashed #cbd5da !important;
  font-weight: 700 !important;
}
.gradio-container button.boundedheight span,
.gradio-container button.boundedheight svg {
  color: var(--ink) !important;
}
.gradio-container label.float {
  background: #ffffff !important;
  color: #243238 !important;
  border-color: var(--line) !important;
}
.gradio-container label.float span,
.gradio-container label.float svg {
  color: #243238 !important;
}
.login-shell {
  max-width: 460px;
  margin: 8vh auto 0;
  padding: 28px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
}
.login-shell,
.login-shell .block,
.login-shell .form,
.login-shell .wrap,
.login-shell .contain,
.login-shell .input-container {
  background: var(--surface) !important;
  color: var(--ink) !important;
  border-color: var(--line) !important;
  box-shadow: none !important;
}
.login-shell h2 {
  color: var(--ink) !important;
  opacity: 1 !important;
}
.login-shell p,
.login-shell .block-info {
  color: #51616a !important;
  opacity: 1 !important;
}
.login-shell label,
.login-shell label span,
.login-shell .block-label {
  color: #243238 !important;
  opacity: 1 !important;
}
.login-shell input {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #cbd5da !important;
  box-shadow: none !important;
}
.login-shell input::placeholder {
  color: #6b7280 !important;
  opacity: 1 !important;
}
.login-shell button,
.login-shell button span {
  color: #ffffff !important;
}
.sidebar { min-width: 310px; border-right: 1px solid var(--line); padding-right: 18px; }
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
.job-language { color: var(--muted); margin-top: 8px; display: flex; gap: 10px; flex-wrap: wrap; }
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
.stage-flow {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.stage-steps {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.stage-step {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 10px;
  color: #51616a;
  font-size: 13px;
  min-height: 54px;
}
.stage-step strong {
  display: block;
  color: var(--ink);
  font-size: 13px;
  margin-bottom: 4px;
}
.stage-step.done { background: #f2f7f6; border-color: #b7d5d1; }
.stage-step.active {
  background: #e8f4f2;
  border-color: var(--teal);
  color: #0b4f49;
}
.stage-step.blocked {
  background: #fff8e8;
  border-color: #e2b96e;
}
.stage-note {
  margin-top: 12px;
  color: #51616a;
  font-size: 14px;
}
.stage-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 12px;
}
.stage-panel h3 {
  color: var(--ink) !important;
  margin-top: 0 !important;
}
.detail-accordion {
  margin-top: 12px;
}
@media (max-width: 600px) {
  .sidebar { min-width: 0 !important; padding-right: 0 !important; border-right: 0 !important; }
  .main-pane { padding-left: 0 !important; }
  .stage-steps { grid-template-columns: 1fr 1fr; }
}
"""

LANGUAGES = [
    ("中文", "zh"),
    ("English", "en"),
    ("日本語", "ja"),
    ("한국어", "ko"),
    ("Francais", "fr"),
    ("Deutsch", "de"),
    ("Espanol", "es"),
    ("Portugues", "pt"),
    ("Russian", "ru"),
    ("Arabic", "ar"),
]


def create_gradio_app() -> gr.Blocks:
    theme = gr.themes.Base(
        primary_hue="teal",
        secondary_hue="amber",
        neutral_hue="gray",
        radius_size="sm",
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
            gr.Markdown("## 登录\n任务由后台 Worker 持续处理，关闭页面不会中断。")
            username = gr.Textbox(label="用户名", lines=1, max_lines=1)
            password = gr.Textbox(label="密码", type="password")
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
                    selected_model = gr.Dropdown(label="翻译模型", choices=[])
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
                    stage_flow = gr.HTML(
                        "", visible=False, elem_classes=["stage-flow"]
                    )

                    with gr.Column(
                        visible=True, elem_classes=["stage-panel"]
                    ) as no_job_panel:
                        gr.Markdown(
                            "### 选择任务或创建新任务\n左侧是并发任务总览。选择任意任务后，右侧会只显示该任务当前阶段需要的操作。"
                        )

                    with gr.Column(
                        visible=False, elem_classes=["stage-panel"]
                    ) as progress_panel:
                        gr.Markdown(
                            "### 后台处理中\nWorker 会持续处理当前任务。你可以关闭页面，稍后重新登录查看进度和下载结果。"
                        )
                        chunks = gr.Dataframe(
                            headers=["序号", "章节", "类型", "状态", "估算 Token", "检查"],
                            datatype=["number", "str", "str", "str", "number", "str"],
                            interactive=False,
                            elem_classes=["compact-table"],
                        )

                    with gr.Column(
                        visible=False, elem_classes=["stage-panel"]
                    ) as terms_panel:
                        gr.Markdown(
                            "### 术语确认\n检查术语建议，必要时编辑“确认译名”，确认后进入预翻译和风格确认。"
                        )
                        terms = gr.Dataframe(
                            headers=["原文术语", "建议译名", "确认译名", "备注", "已确认"],
                            datatype=["str", "str", "str", "str", "bool"],
                            type="array",
                            interactive=True,
                            elem_classes=["compact-table"],
                        )
                        confirm_terms_button = gr.Button(
                            "确认术语并生成预翻译", variant="primary"
                        )

                    with gr.Column(
                        visible=False, elem_classes=["stage-panel"]
                    ) as style_panel:
                        gr.Markdown(
                            "### 预翻译与风格确认\n先查看样例译文，再填写或调整风格 Prompt。确认后正式进入全文翻译。"
                        )
                        style_prompt = gr.Textbox(label="风格 Prompt", lines=4)
                        with gr.Row():
                            retry_preview_button = gr.Button("重新预翻译")
                            confirm_style_button = gr.Button(
                                "确认风格并继续", variant="primary"
                            )
                        with gr.Row():
                            preview_source = gr.Textbox(
                                label="预翻译原文样例", lines=12, interactive=False
                            )
                            preview_translation = gr.Textbox(
                                label="预翻译结果", lines=12, interactive=False
                            )

                    with gr.Column(
                        visible=False, elem_classes=["stage-panel"]
                    ) as review_panel:
                        gr.Markdown(
                            "### 人工审核\n当前任务暂停在风险或章节确认点。处理后 Worker 会继续执行。"
                        )
                        reviews = gr.Dataframe(
                            headers=["类型", "位置", "状态", "备注"],
                            datatype=["str"] * 4,
                            interactive=False,
                            elem_classes=["compact-table"],
                        )
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
                        review_note = gr.Textbox(label="审核备注", lines=2)
                        approve_review_button = gr.Button(
                            "接受当前风险并继续", variant="primary"
                        )

                    with gr.Column(
                        visible=False, elem_classes=["stage-panel"]
                    ) as output_panel:
                        gr.Markdown(
                            "### 结果与交付\n任务完成后可以下载结果；如需微调译文，可编辑片段并重新生成输出。"
                        )
                        with gr.Row():
                            bilingual_html = gr.File(label="双语 HTML", interactive=False)
                            translated_html = gr.File(label="译文 HTML", interactive=False)
                            package = gr.File(label="完整结果包", interactive=False)
                        with gr.Row():
                            bilingual = gr.File(label="双语 Markdown", interactive=False)
                            translated = gr.File(label="译文 Markdown", interactive=False)
                            report = gr.File(label="翻译报告", interactive=False)
                            source = gr.File(label="原始文件", interactive=False)
                        edit_chunk = gr.Dropdown(label="片段")
                        with gr.Row():
                            edit_source = gr.Textbox(
                                label="原文", lines=14, interactive=False
                            )
                            edit_translation = gr.Textbox(label="当前译文", lines=14)
                        edit_note = gr.Textbox(label="编辑备注", lines=2)
                        with gr.Row():
                            load_chunk_button = gr.Button("加载片段")
                            save_translation_button = gr.Button(
                                "保存译文", variant="primary"
                            )
                            regenerate_outputs_button = gr.Button("重新生成输出")
                        versions = gr.Dataframe(
                            headers=[
                                "版本 ID",
                                "版本号",
                                "来源",
                                "时间",
                                "模型",
                                "备注",
                            ],
                            datatype=["str", "number", "str", "str", "str", "str"],
                            interactive=False,
                            elem_classes=["compact-table"],
                        )
                        restore_version_id = gr.Textbox(label="要恢复的版本 ID")
                        restore_version_button = gr.Button("恢复该版本")

                    with gr.Accordion(
                        "任务详情和高级信息",
                        open=False,
                        elem_classes=["detail-accordion"],
                    ):
                        with gr.Tabs():
                            with gr.Tab("术语"):
                                detail_terms = gr.Dataframe(
                                    headers=["原文术语", "建议译名", "确认译名", "备注", "已确认"],
                                    datatype=["str", "str", "str", "str", "bool"],
                                    interactive=False,
                                    elem_classes=["compact-table"],
                                )
                            with gr.Tab("分块"):
                                detail_chunks = gr.Dataframe(
                                    headers=["序号", "章节", "类型", "状态", "估算 Token", "检查"],
                                    datatype=["number", "str", "str", "str", "number", "str"],
                                    interactive=False,
                                    elem_classes=["compact-table"],
                                )
                            with gr.Tab("风险"):
                                detail_risks = gr.Dataframe(
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
                                detail_reviews = gr.Dataframe(
                                    headers=["类型", "位置", "状态", "备注"],
                                    datatype=["str"] * 4,
                                    interactive=False,
                                    elem_classes=["compact-table"],
                                )
                            with gr.Tab("时间线"):
                                events = gr.Dataframe(
                                    headers=["时间", "阶段", "状态", "耗时", "说明"],
                                    datatype=["str"] * 5,
                                    interactive=False,
                                    elem_classes=["compact-table"],
                                )

        dashboard_outputs = [
            job_summary,
            stage_flow,
            no_job_panel,
            progress_panel,
            terms_panel,
            style_panel,
            review_panel,
            output_panel,
            terms,
            chunks,
            risks,
            events,
            reviews,
            preview_source,
            preview_translation,
            style_prompt,
            edit_chunk,
            edit_source,
            edit_translation,
            versions,
            bilingual,
            translated,
            report,
            bilingual_html,
            translated_html,
            package,
            source,
            detail_terms,
            detail_chunks,
            detail_risks,
            detail_reviews,
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

        demo.load(handlers.model_choices, outputs=selected_model)
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
                selected_model,
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
        retry_preview_button.click(
            handlers.retry_pretranslation,
            inputs=[auth_token, selected_job, style_prompt],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        confirm_style_button.click(
            handlers.confirm_style,
            inputs=[auth_token, selected_job, style_prompt],
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
        load_chunk_button.click(
            handlers.load_chunk_for_edit,
            inputs=[auth_token, selected_job, edit_chunk],
            outputs=[edit_source, edit_translation, versions, operation_status],
        )
        edit_chunk.change(
            handlers.load_chunk_for_edit,
            inputs=[auth_token, selected_job, edit_chunk],
            outputs=[edit_source, edit_translation, versions, operation_status],
        )
        save_translation_button.click(
            handlers.save_chunk_translation,
            inputs=[auth_token, selected_job, edit_chunk, edit_translation, edit_note],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        restore_version_button.click(
            handlers.restore_chunk_version,
            inputs=[auth_token, selected_job, edit_chunk, restore_version_id],
            outputs=operation_status,
        ).then(
            handlers.refresh_dashboard,
            inputs=[auth_token, selected_job],
            outputs=dashboard_outputs,
        )
        regenerate_outputs_button.click(
            handlers.regenerate_outputs,
            inputs=[auth_token, selected_job],
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
