"""研究结果工作台 - 查看分类结果、筛选排序、导出到 Obsidian。"""

import streamlit as st
from ui.api_client import APIClient


# === Helper Functions (must be defined before Streamlit execution) ===


def classify_report_ingestion_sources(items: list[dict]) -> dict[str, list[dict]]:
    """对 report_ingestion 任务的来源按 source_origin 分类。"""
    categories = {
        "报告中直接链接": [],
        "补充检索来源": [],
        "提取失败 / 需手动处理": [],
    }
    for item in items:
        origin = item.get("source_origin", "search_provider")
        dl_status = item.get("download_status", "pending")

        if dl_status == "failed":
            categories["提取失败 / 需手动处理"].append(item)
        elif origin == "imported_report":
            categories["报告中直接链接"].append(item)
        elif origin == "imported_report_enriched":
            categories["补充检索来源"].append(item)
        else:
            categories["报告中直接链接"].append(item)

    return {k: v for k, v in categories.items() if v}


def get_source_origin_label(origin: str) -> str:
    """获取 source_origin 的中文标签。"""
    labels = {
        "imported_report": "📥 报告直接引用",
        "imported_report_enriched": "🔍 补充检索",
        "search_provider": "🔎 搜索引擎",
        "manual": "✏️ 手动添加",
    }
    return labels.get(origin, origin)


def _render_source_list(items: list[dict], api_client: APIClient, show_origin: bool = False, key_prefix: str = ""):
    """渲染来源列表。"""
    if not items:
        st.info("暂无来源。")
        return

    for item in items:
        level = item.get("source_level", "?")
        level_emoji = {"S": "🏆", "A": "⭐", "B": "📄", "C": "📎", "D": "⚠️"}.get(level, "📄")
        title = item.get("title", "无标题")[:100]
        url = item.get("url", "")
        domain = item.get("domain", "")
        snippet = item.get("snippet", "")
        source_type = item.get("source_type", "")
        reason = item.get("reason_to_read", "")
        dl_status = item.get("download_status", "pending")

        with st.container():
            st.markdown(f"{level_emoji} **[{level}]** [{title}]({url})")
            detail_parts = []
            if domain:
                detail_parts.append(f"🌐 {domain}")
            if source_type:
                detail_parts.append(f"📁 {source_type}")
            if show_origin:
                origin = item.get("source_origin", "")
                if origin:
                    detail_parts.append(get_source_origin_label(origin))
            if item.get("crawl_status") and item["crawl_status"] != "pending":
                crawl_badge = {"succeeded": "🕷️✅", "failed": "🕷️❌", "skipped": "🕷️⏭️", "crawling": "🕷️⏳"}.get(item["crawl_status"], "")
                if crawl_badge:
                    detail_parts.append(crawl_badge)
            if reason:
                detail_parts.append(f"💡 {reason}")
            if detail_parts:
                st.caption(" | ".join(detail_parts))
            if snippet:
                st.caption(snippet[:200])

            scores_col, action_col = st.columns([3, 1])
            with scores_col:
                rel = item.get("relevance_score", 0)
                auth = item.get("authority_score", 0)
                orig = item.get("originality_score", 0)
                gossip = item.get("gossip_score", 0)
                if rel or auth or orig:
                    st.caption(f"相关性: {rel:.2f} | 权威性: {auth:.2f} | 原创性: {orig:.2f}" +
                              (f" | 八卦: {gossip:.2f}" if gossip > 0 else ""))
            with action_col:
                if dl_status == "pending":
                    if st.button("📥 提取", key=f"{key_prefix}extract_{item['id']}"):
                        with st.spinner("提取中..."):
                            try:
                                result = api_client.extract_source(item["id"])
                                if result.get("status") == "extracted":
                                    st.success(f"✅ 提取成功（{result.get('content_length', 0)} 字）")
                                elif result.get("status") == "skipped":
                                    st.warning(result.get("error", "已跳过"))
                                else:
                                    st.error(result.get("error", "提取失败"))
                            except Exception as e:
                                st.error(f"失败: {e}")
                elif dl_status in ("extracted", "exported"):
                    st.caption("✅ 已提取")
                elif dl_status == "failed":
                    st.caption("❌ 失败")
                elif dl_status == "skipped":
                    st.caption("⏭️ 跳过")

            # 已提取的来源：显示可展开的内容预览
            if dl_status in ("extracted", "exported"):
                with st.expander("👁️ 查看提取内容", expanded=False):
                    try:
                        content_data = api_client.get_extracted_content(item["id"])
                        if content_data.get("found"):
                            if content_data.get("summary"):
                                st.markdown(f"**摘要：** {content_data['summary']}")
                            if content_data.get("people"):
                                st.markdown(f"**人物：** {', '.join(content_data['people'][:10])}")
                            if content_data.get("concepts"):
                                st.markdown(f"**概念：** {', '.join(content_data['concepts'][:10])}")
                            if content_data.get("key_quotes"):
                                st.markdown("**关键摘录：**")
                                for q in content_data["key_quotes"][:3]:
                                    st.markdown(f"> {q}")
                            content_text = content_data.get("content", "")
                            if content_text:
                                st.text_area(
                                    "正文预览",
                                    value=content_text[:3000],
                                    height=200,
                                    key=f"{key_prefix}content_{item['id']}",
                                    disabled=True,
                                )
                            st.caption(f"总字数：{content_data.get('content_length', 0)}")
                        else:
                            st.caption("内容未找到")
                    except Exception as e:
                        st.caption(f"加载失败: {e}")
            st.divider()


def _render_index_preview(task: dict, items: list[dict]):
    """渲染研究索引预览。"""
    topic = task.get("topic", "未知主题")
    s_a = [i for i in items if i["source_level"] in ("S", "A")]
    books = [i for i in items if i["source_type"] == "book"]
    gossip = [i for i in items if i.get("gossip_score", 0) >= 0.3]

    preview = f"# {topic}｜研究索引预览\n\n"
    preview += "## 研究概览\n"
    preview += f"- 来源总数：{len(items)}\n"
    preview += f"- 高质量来源 (S/A)：{len(s_a)}\n"
    preview += f"- 图书资料：{len(books)}\n"
    preview += f"- 八卦与旁证：{len(gossip)}\n\n"

    if s_a:
        preview += "## 必读资料\n"
        for item in s_a[:10]:
            preview += f"- **[{item['source_level']}]** [{item['title'][:60]}]({item['url']})\n"
            if item.get("reason_to_read"):
                preview += f"  - {item['reason_to_read']}\n"
        preview += "\n"
    if books:
        preview += "## 图书资料\n"
        for item in books[:5]:
            preview += f"- [{item['title'][:60]}]({item['url']})\n"
        preview += "\n"
    if gossip:
        preview += "## 八卦与旁证\n"
        preview += "> 以下内容只作为线索，不应直接当作事实使用。\n\n"
        for item in gossip[:5]:
            preview += f"- [{item['title'][:60]}]({item['url']})\n"
        preview += "\n"
    preview += "## 下一步建议\n"
    preview += "- 先提取 S/A 级来源正文\n"
    preview += "- 再导出研究索引到 Obsidian\n"
    preview += "- 再批量分析文档\n"
    st.markdown(preview)


def _render_llm_task_line(task_info: dict, status_badges: dict):
    """渲染单条 LLM 任务状态行。"""
    status = task_info.get("status", "unknown")
    badge = status_badges.get(status, "❓")
    task_name = task_info.get("task_name", "?")
    stage = task_info.get("stage", "")
    line = f"{badge} **{task_name}** ({stage})"

    if status == "used_llm":
        provider = task_info.get("provider", "")
        model = task_info.get("model", "")
        duration = task_info.get("duration_ms")
        input_c = task_info.get("input_chars")
        output_c = task_info.get("output_chars")
        details = f"{provider}/{model}"
        if duration:
            details += f" {duration}ms"
        if input_c and output_c:
            details += f" ({input_c}→{output_c} chars)"
        line += f" — {details}"
    elif status == "fallback":
        fallback = task_info.get("fallback_name", "")
        line += f" — fallback: {fallback}"
    st.markdown(line)


def _render_llm_usage(task_id: str, api_client: APIClient):
    """渲染 LLM 使用情况区域（分组展示）。"""
    try:
        llm_data = api_client.get_trace_llm(task_id)
    except Exception as e:
        st.caption(f"无法加载 LLM 详情：{e}")
        return

    st.caption(f"Active Provider: **{llm_data.get('active_provider', '—')}** / Model: **{llm_data.get('active_model', '—')}** / 实际调用: **{llm_data.get('llm_call_count', 0)}** 次")

    llm_tasks = llm_data.get("llm_tasks", [])
    if not llm_tasks:
        st.info("本次研究未记录 LLM 任务状态。")
        return

    status_badges = {
        "used_llm": "✅", "fallback": "🔁", "skipped_not_reached": "⏭️",
        "skipped_disabled": "🚫", "skipped_not_implemented": "🧩",
        "skipped_missing_prompt": "⚠️", "rule_only": "⚙️",
        "covered_by": "🔗", "waiting": "⏳",
    }

    # 分组
    groups = {
        "executed": [],
        "covered": [],
        "waiting": [],
        "export": [],
        "disabled": [],
        "planned": [],
    }
    for task_info in llm_tasks:
        group = task_info.get("group", "executed")
        if group not in groups:
            groups[group] = []
        groups[group].append(task_info)

    # 本次已执行
    if groups["executed"]:
        st.markdown("**本次已执行：**")
        for task_info in groups["executed"]:
            _render_llm_task_line(task_info, status_badges)

    # 由其他任务覆盖
    if groups["covered"]:
        for task_info in groups["covered"]:
            covered = task_info.get("covered_by", "")
            st.caption(f"🔗 **{task_info['task_name']}** — 由 {covered} 覆盖")

    # 等待后续阶段
    if groups["waiting"]:
        st.markdown("**等待后续阶段：**")
        for task_info in groups["waiting"]:
            wait = task_info.get("wait_for", "")
            st.caption(f"⏳ **{task_info['task_name']}** ({task_info.get('stage', '')}) — 等待{wait}")

    # 导出阶段
    if groups["export"]:
        st.markdown("**导出阶段：**")
        for task_info in groups["export"]:
            status = task_info.get("status", "")
            if status == "used_llm":
                _render_llm_task_line(task_info, status_badges)
            else:
                st.caption(f"📤 **{task_info['task_name']}** — 导出时触发")

    # 已禁用
    if groups["disabled"]:
        with st.expander(f"🚫 已禁用 ({len(groups['disabled'])})", expanded=False):
            for task_info in groups["disabled"]:
                st.caption(f"🚫 **{task_info['task_name']}** — {task_info.get('skipped_reason', '')}")

    # 规划中
    if groups["planned"]:
        with st.expander(f"🧩 规划中能力 ({len(groups['planned'])})", expanded=False):
            for task_info in groups["planned"]:
                st.caption(f"🧩 **{task_info['task_name']}** ({task_info.get('stage', '')}) — 规划中")

    rule_steps = llm_data.get("rule_only_steps", [])
    if rule_steps:
        st.caption(f"⚙️ 规则步骤（不使用 LLM）: {', '.join(rule_steps)}")


def _render_trace_view(task_id: str, api_client: APIClient):
    """渲染执行流程 / Trace 视图。"""

    # 步骤中文映射
    _step_zh = {
        "task_created": "任务已创建",
        "llm_plan_created": "AI 能力规划完成",
        "language_planning_finished": "语言规划完成",
        "llm_call_started": "正在调用 AI",
        "llm_call_finished": "AI 调用完成",
        "llm_call_failed": "AI 调用失败",
        "query_expansion_finished": "搜索词扩展完成",
        "search_provider_started": "正在搜索",
        "search_provider_finished": "搜索完成",
        "search_provider_failed": "搜索失败",
        "dedupe_finished": "去重完成",
        "scoring_finished": "来源评分完成",
        "task_completed": "研究完成",
        "task_failed": "研究失败",
        "auto_fetch_started": "开始自动抓取正文",
        "auto_fetch_source_started": "正在抓取来源",
        "auto_fetch_source_finished": "来源抓取成功",
        "auto_fetch_source_failed": "来源抓取失败",
        "auto_fetch_finished": "自动抓取完成",
        "auto_analysis_started": "开始 AI 分析",
        "auto_analysis_finished": "AI 分析完成",
        "auto_export_started": "开始导出到 Obsidian",
        "auto_export_finished": "导出完成",
        "auto_export_failed": "导出失败",
        # Crawlee 阶段
        "crawl_candidates_collected": "搜索候选已收集",
        "crawl_candidate_review_started": "开始候选相关性审查",
        "crawl_candidate_review_finished": "候选审查完成",
        "crawl_candidate_skipped": "候选已跳过",
        "crawlee_batch_started": "开始 Crawlee 批量抓取",
        "crawlee_url_started": "正在抓取 URL",
        "crawlee_url_finished": "URL 抓取成功",
        "crawlee_url_failed": "URL 抓取失败",
        "crawlee_batch_finished": "Crawlee 批量抓取完成",
        "crawl_saved_document": "抓取文档已保存",
        "crawl_auto_export_started": "开始抓取结果导出",
        "crawl_auto_export_finished": "抓取结果导出完成",
    }

    try:
        summary = api_client.get_trace_summary(task_id)
    except Exception as e:
        st.warning(f"无法加载 Trace 摘要：{e}")
        return

    if summary.get("total_events", 0) == 0:
        st.info("暂无执行轨迹数据。")
        return

    col1, col2, col3, col4, col5 = st.columns(5)
    duration = summary.get("duration_ms")
    col1.metric("总耗时", f"{duration / 1000:.1f}s" if duration else "—")
    col2.metric("LLM 调用", summary.get("llm_calls", 0))
    col3.metric("搜索调用", summary.get("search_calls", 0))
    col4.metric("⚠️ Warning", summary.get("warning_count", 0))
    col5.metric("❌ Error", summary.get("error_count", 0))

    providers = summary.get("providers_used", [])
    if providers:
        st.caption(f"使用的服务: {', '.join(providers)}")
    source_counts = summary.get("source_counts", {})
    level_counts = summary.get("level_counts", {})
    if source_counts:
        st.caption(f"来源: 原始 {source_counts.get('raw', 0)} → 去重后 {source_counts.get('deduped', 0)}")
    if level_counts:
        parts = [f"{k}={v}" for k, v in sorted(level_counts.items())]
        st.caption(f"等级分布: {', '.join(parts)}")

    st.markdown("---")
    st.markdown("### 🤖 LLM 使用情况")
    _render_llm_usage(task_id, api_client)
    st.markdown("---")

    fcol1, fcol2 = st.columns(2)
    with fcol1:
        trace_phase = st.selectbox("阶段", ["全部", "planning", "llm", "search", "processing", "storage", "extraction", "export"], key="trace_phase")
    with fcol2:
        trace_level = st.selectbox("级别", ["全部", "info", "warning", "error"], key="trace_level")

    try:
        params = {}
        if trace_phase != "全部":
            params["phase"] = trace_phase
        if trace_level != "全部":
            params["level"] = trace_level
        trace_data = api_client.get_trace(task_id, **params)
        events = trace_data.get("events", [])
    except Exception as e:
        st.warning(f"无法加载 Trace 事件：{e}")
        return

    if not events:
        st.info("无匹配事件。")
        return

    for event in events:
        level = event.get("level", "info")
        icon = {"info": "✅", "warning": "⚠️", "error": "❌", "debug": "🔍"}.get(level, "ℹ️")
        step = event.get("step", "")
        message = event.get("message", "")
        evt_duration = event.get("duration_ms")
        provider = event.get("provider")

        line_parts = [f"{icon} **{_step_zh.get(step, step)}**"]
        if message:
            line_parts.append(f"— {message}")
        if evt_duration:
            line_parts.append(f"({evt_duration}ms)")
        if provider:
            line_parts.append(f"[{provider}]")
        st.markdown(" ".join(line_parts))

        has_details = event.get("input_summary") or event.get("output_summary") or event.get("metrics") or event.get("error_message")
        if has_details:
            with st.expander("详情", expanded=False):
                if event.get("input_summary"):
                    st.json(event["input_summary"])
                if event.get("output_summary"):
                    st.json(event["output_summary"])
                if event.get("metrics"):
                    st.json(event["metrics"])
                if event.get("error_message"):
                    st.error(event["error_message"])


# === Page Execution Starts Here ===

st.header("📊 研究结果")

client = APIClient()

# === 历史任务列表（侧边栏） ===

with st.sidebar:
    st.subheader("📚 历史研究任务")

    # 搜索和筛选
    history_q = st.text_input("搜索主题", key="history_search", placeholder="输入关键词...")
    history_status = st.selectbox(
        "状态筛选",
        ["全部", "completed", "running", "pending", "failed"],
        key="history_status",
    )

    col_refresh, col_deleted = st.columns(2)
    with col_refresh:
        if st.button("🔄 刷新", key="refresh_history", use_container_width=True):
            pass  # 触发 rerun
    with col_deleted:
        show_deleted = st.checkbox("显示已删除", key="show_deleted_tasks")

    # 获取任务列表
    try:
        status_filter = history_status if history_status != "全部" else None
        q_filter = history_q if history_q else None
        tasks_data = client.list_tasks(limit=30, status=status_filter, q=q_filter, include_deleted=show_deleted)
        history_tasks = tasks_data.get("items", [])
    except Exception:
        history_tasks = []

    if history_tasks:
        for ht in history_tasks:
            is_deleted = ht.get("deleted_at") is not None
            status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(ht["status"], "❓")
            if is_deleted:
                status_icon = "🗑️"
            topic_short = ht["topic"][:25] + ("..." if len(ht["topic"]) > 25 else "")
            source_info = f"{ht.get('source_count', 0)} sources"
            hq = ht.get("high_quality_count", 0)
            if hq:
                source_info += f" · {hq} S/A"
            export_badge = " · 📤" if ht.get("exported") else ""
            cloned_badge = " · 📋" if ht.get("cloned_from_task_id") else ""
            time_str = (ht.get("created_at") or "")[:10]

            if st.button(
                f"{status_icon} {topic_short}",
                key=f"hist_{ht['task_id']}",
                help=f"{ht['topic']} | {ht['status']} | {source_info}{cloned_badge}",
                use_container_width=True,
            ):
                st.session_state["selected_task_id"] = ht["task_id"]
                st.rerun()

        st.caption(f"共 {tasks_data.get('total', 0)} 个任务")
    else:
        st.caption("暂无研究任务。")

# === Task ID 选择逻辑 ===

# 优先级：selected_task_id > last_task_id > 手动输入
selected_id = st.session_state.get("selected_task_id", "") or st.session_state.get("last_task_id", "")

task_id = st.text_input("Task ID", value=selected_id, placeholder="输入任务 ID 或从左侧选择")

if not task_id.strip():
    if history_tasks:
        # 自动选择第一个 completed 任务
        completed = [t for t in history_tasks if t["status"] == "completed"]
        if completed:
            task_id = completed[0]["task_id"]
        else:
            task_id = history_tasks[0]["task_id"]
    else:
        st.info("请输入 Task ID 或先在 Research 页面创建任务。")
        st.stop()

task_id = task_id.strip()

# === 加载任务状态 ===

try:
    task = client.get_task(task_id)
except Exception as e:
    st.error(f"获取任务失败：{e}")
    st.stop()

# === 顶部状态区域 ===

status = task["status"]
status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(status, "❓")

st.subheader(f"{status_icon} {task['topic']}")

col1, col2, col3, col4 = st.columns(4)
col1.markdown(f"**模式**: {task['mode']}")
col2.markdown(f"**状态**: {status}")
col3.markdown(f"**创建**: {(task.get('created_at') or '')[:16]}")
col4.markdown(f"**完成**: {(task.get('completed_at') or '—')[:16]}")

if status != "completed":
    st.warning(f"任务状态为 `{status}`，结果可能不完整。")

# === 任务管理操作 ===

with st.expander("🛠️ 任务管理", expanded=False):
    mgmt_col1, mgmt_col2, mgmt_col3 = st.columns(3)

    # 重命名
    with mgmt_col1:
        st.markdown("**✏️ 重命名**")
        new_topic = st.text_input(
            "新主题名称",
            value=task["topic"],
            key="rename_topic_input",
            label_visibility="collapsed",
        )
        if st.button("保存名称", key="btn_rename"):
            if new_topic.strip() and new_topic.strip() != task["topic"]:
                try:
                    result = client.rename_task(task_id, new_topic.strip())
                    st.success(f"✅ {result.get('message', '已重命名')}")
                    st.rerun()
                except Exception as e:
                    st.error(f"重命名失败: {e}")
            elif not new_topic.strip():
                st.warning("主题名称不能为空")

    # 复制重跑
    with mgmt_col2:
        st.markdown("**📋 复制并重新研究**")
        clone_topic = st.text_input(
            "新任务主题（可选）",
            value="",
            key="clone_topic_input",
            placeholder="留空则使用原主题",
            label_visibility="collapsed",
        )
        clone_col_a, clone_col_b = st.columns(2)
        with clone_col_a:
            if st.button("仅复制", key="btn_clone_only"):
                try:
                    override = clone_topic.strip() if clone_topic.strip() else None
                    result = client.clone_task(task_id, topic_override=override, rerun_immediately=False)
                    new_id = result.get("new_task_id", "")
                    st.success(f"✅ 已复制，新任务: {new_id[:8]}...")
                    st.session_state["selected_task_id"] = new_id
                    st.rerun()
                except Exception as e:
                    st.error(f"复制失败: {e}")
        with clone_col_b:
            if st.button("复制并运行", key="btn_clone_run"):
                try:
                    override = clone_topic.strip() if clone_topic.strip() else None
                    result = client.clone_task(task_id, topic_override=override, rerun_immediately=True)
                    new_id = result.get("new_task_id", "")
                    st.success(f"✅ 已复制，新任务: {new_id[:8]}...")
                    # 触发运行
                    try:
                        client.run_research(new_id)
                    except Exception:
                        pass
                    st.session_state["selected_task_id"] = new_id
                    st.rerun()
                except Exception as e:
                    st.error(f"复制并运行失败: {e}")

    # 删除
    with mgmt_col3:
        st.markdown("**🗑️ 删除任务**")
        st.caption("此操作只会从历史列表中隐藏该任务，不会删除 Obsidian 中已导出的文件。")
        confirm_delete = st.checkbox("我确认删除该任务", key="confirm_delete_checkbox")
        if st.button("删除任务", key="btn_delete", type="secondary", disabled=not confirm_delete):
            try:
                result = client.delete_task(task_id)
                st.success(f"✅ {result.get('message', '已删除')}")
                st.session_state.pop("selected_task_id", None)
                st.rerun()
            except Exception as e:
                st.error(f"删除失败: {e}")

# === 报告导入 badge 和摘要 ===

_is_report_ingestion = task.get("task_type") == "report_ingestion"

if _is_report_ingestion:
    st.markdown("📥 **外部研究报告导入**")
    try:
        _report_detail = client.get_imported_report(task_id)
        _report_source = _report_detail.get("report_source") or "未知来源"
        st.caption(f"报告来源: **{_report_source}**")
    except Exception:
        _report_detail = None

st.divider()

# === 加载来源 ===

try:
    sources_data = client.get_sources(task_id)
except Exception as e:
    st.error(f"获取来源失败：{e}")
    st.stop()

categories = sources_data.get("categories", {})
all_items = sources_data.get("items", [])
total = sources_data.get("total", 0)

has_sources = total > 0

if not has_sources:
    st.info("暂无来源数据。请先运行研究任务。")

# === 执行流程 Trace（始终显示，不受来源数据影响） ===

st.divider()
with st.expander("🧭 执行流程 / Research Trace", expanded=not has_sources):
    _render_trace_view(task_id, client)

st.divider()

if not has_sources:
    # 事件日志也始终可见
    with st.expander("📋 任务事件日志", expanded=False):
        try:
            events_data = client.get_events(task_id, limit=30)
            events = events_data.get("events", [])
            if events:
                for event in events:
                    level = event.get("level", "info")
                    icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
                    time_str = event.get("created_at", "")[:19].replace("T", " ")
                    st.caption(f"{icon} `{time_str}` **{event['event_type']}** — {event['message']}")
            else:
                st.info("暂无事件记录。")
        except Exception as e:
            st.warning(f"无法加载事件日志：{e}")
    st.stop()

# === 统计卡片 ===

st.subheader("📈 研究概览")

s_a_items = [i for i in all_items if i["source_level"] in ("S", "A")]
book_items = [i for i in all_items if i["source_type"] == "book"]
extracted_items = [i for i in all_items if i["download_status"] in ("extracted", "exported")]
gossip_items = [i for i in all_items if i.get("gossip_score", 0) >= 0.3]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("总来源", total)

# 可点击的筛选指标
with col2:
    if st.button(f"**{len(s_a_items)}**\n\n高质量 (S/A)", key="filter_sa", use_container_width=True):
        st.session_state["_filter_preset"] = "high_quality"

with col3:
    if st.button(f"**{len(book_items)}**\n\n图书资料", key="filter_books", use_container_width=True):
        st.session_state["_filter_preset"] = "books"

with col4:
    if st.button(f"**{len(extracted_items)}**\n\n已提取正文", key="filter_extracted", use_container_width=True):
        st.session_state["_filter_preset"] = "extracted"

with col5:
    if st.button(f"**{len(gossip_items)}**\n\n八卦线索", key="filter_gossip", use_container_width=True):
        st.session_state["_filter_preset"] = "gossip"

# 处理筛选预设
_filter_preset = st.session_state.get("_filter_preset")

if _is_report_ingestion:
    # 报告导入特有的统计
    imported_direct = [i for i in all_items if i.get("source_origin") == "imported_report"]
    enriched = [i for i in all_items if i.get("source_origin") == "imported_report_enriched"]
    failed_items = [i for i in all_items if i.get("download_status") == "failed"]

    st.markdown("**导入摘要：**")
    ri_col1, ri_col2, ri_col3 = st.columns(3)
    ri_col1.metric("报告直接链接", len(imported_direct))
    ri_col2.metric("补充检索来源", len(enriched))
    ri_col3.metric("提取失败", len(failed_items))

st.divider()

# === 导出到 Obsidian ===

st.subheader("📤 导出到 Obsidian")

if status != "completed":
    st.warning("⏳ 研究任务尚未完成，完成后才能导出。")
else:
    try:
        obsidian_config = client.get_obsidian_settings()
        vault_configured = obsidian_config.get("configured", False)
        vault_exists = obsidian_config.get("exists", False)
        vault_writable = obsidian_config.get("writable", False)
        vault_path = obsidian_config.get("vault_path", "")
        vault_usable = vault_configured and vault_exists and vault_writable
    except Exception:
        vault_usable = False
        vault_configured = False
        vault_path = ""

    if vault_usable:
        st.markdown(f"✅ Vault 可用: `{vault_path}`")
        st.caption(f"导出目标: `{vault_path}/Research/{task['topic']}/index.md`")

        col_export1, col_export2 = st.columns(2)
        with col_export1:
            if st.button("📄 导出研究索引到 Obsidian", type="primary", key="export_index_btn"):
                with st.spinner("正在导出研究索引..."):
                    try:
                        result = client.export_index(task_id)
                        if result.get("success"):
                            st.success(f"✅ 已导出到: `{result.get('path', '')}`")
                            st.caption(f"包含 {result.get('source_count', 0)} 个来源")
                        else:
                            st.error(f"导出失败: {result.get('message', '未知错误')}")
                    except Exception as e:
                        error_msg = str(e)
                        if "400" in error_msg:
                            st.error("导出失败: Vault 配置问题")
                        else:
                            st.error(f"导出失败: {e}")

        with col_export2:
            st.caption("研究索引包含：必读资料、图书资料、访谈资料、八卦线索等分类清单。")
    elif vault_configured:
        st.warning(f"⚠️ Vault 路径无效: `{vault_path}`")
        st.page_link("pages/9_Settings.py", label="前往 Settings 配置 Vault", icon="⚙️")
    else:
        st.info("📁 Obsidian Vault 未配置，导出功能不可用。请先到 Settings 配置默认 Obsidian Vault。")
        st.page_link("pages/9_Settings.py", label="前往 Settings 配置 Vault", icon="⚙️")

st.divider()

# === 筛选与排序 ===

st.subheader("🔍 筛选与排序")

# 如果有筛选预设，显示清除按钮
if _filter_preset:
    preset_labels = {
        "high_quality": "🏆 高质量 (S/A)",
        "books": "📚 图书资料",
        "extracted": "✅ 已提取正文",
        "gossip": "🗣️ 八卦线索",
    }
    col_label, col_clear = st.columns([4, 1])
    with col_label:
        st.info(f"当前筛选：{preset_labels.get(_filter_preset, _filter_preset)}")
    with col_clear:
        if st.button("✕ 清除", key="clear_filter"):
            del st.session_state["_filter_preset"]
            st.rerun()

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

with filter_col1:
    _default_level = 0
    if _filter_preset == "high_quality":
        _default_level = 0  # 会在后面用代码过滤
    level_filter = st.selectbox(
        "来源等级",
        ["全部", "S", "A", "B", "C", "D"],
        index=_default_level,
        key="level_filter",
    )

with filter_col2:
    type_options = ["全部"] + sorted(set(i["source_type"] for i in all_items))
    _default_type = 0
    if _filter_preset == "books" and "book" in type_options:
        _default_type = type_options.index("book")
    type_filter = st.selectbox("来源类型", type_options, index=_default_type, key="type_filter")

with filter_col3:
    _default_status = 0
    if _filter_preset == "extracted":
        _default_status = 0  # 会在后面用代码过滤
    status_filter = st.selectbox(
        "下载状态",
        ["全部", "pending", "extracted", "exported", "failed"],
        index=_default_status,
        key="status_filter",
    )

with filter_col4:
    sort_by = st.selectbox(
        "排序",
        ["综合质量", "relevance_score", "authority_score", "source_level"],
        index=0,
        key="sort_by",
    )

keyword = st.text_input("关键词搜索（标题/域名/摘要）", key="keyword_filter", placeholder="输入关键词...")

hide_low = st.checkbox("隐藏低质量来源 (D 级)", value=True, key="hide_low")

# 应用筛选
filtered = all_items.copy()

# 应用预设筛选（优先于下拉框）
if _filter_preset == "high_quality":
    filtered = [i for i in filtered if i["source_level"] in ("S", "A")]
elif _filter_preset == "gossip":
    filtered = [i for i in filtered if i.get("gossip_score", 0) >= 0.3]
elif _filter_preset == "extracted":
    filtered = [i for i in filtered if i["download_status"] in ("extracted", "exported")]
elif _filter_preset == "books":
    filtered = [i for i in filtered if i["source_type"] == "book"]
else:
    # 正常下拉框筛选
    if level_filter != "全部":
        filtered = [i for i in filtered if i["source_level"] == level_filter]
    if type_filter != "全部":
        filtered = [i for i in filtered if i["source_type"] == type_filter]
    if status_filter != "全部":
        filtered = [i for i in filtered if i["download_status"] == status_filter]

if hide_low and not _filter_preset:
    filtered = [i for i in filtered if i["source_level"] != "D"]
if keyword:
    kw = keyword.lower()
    filtered = [
        i for i in filtered
        if kw in i.get("title", "").lower()
        or kw in i.get("domain", "").lower()
        or kw in i.get("snippet", "").lower()
    ]

# 排序
level_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
if sort_by == "综合质量":
    filtered.sort(key=lambda x: (
        level_order.get(x["source_level"], 4),
        -(x.get("relevance_score", 0) + x.get("authority_score", 0) + x.get("originality_score", 0)),
    ))
elif sort_by == "relevance_score":
    filtered.sort(key=lambda x: -x.get("relevance_score", 0))
elif sort_by == "authority_score":
    filtered.sort(key=lambda x: -x.get("authority_score", 0))
elif sort_by == "source_level":
    filtered.sort(key=lambda x: level_order.get(x["source_level"], 4))

st.caption(f"显示 {len(filtered)} / {total} 条来源")

st.divider()

# === 分类 Tabs ===

st.subheader("📂 分类浏览")

# 构建 tab 列表
tab_names = ["全部来源"]

if _is_report_ingestion:
    # 报告导入任务使用 source_origin 分类
    ri_categories = classify_report_ingestion_sources(all_items)
    available_cats = list(ri_categories.keys())
    tab_names.extend(available_cats)
else:
    display_categories = ["必读资料", "一手资料", "深度报道", "图书资料", "采访与演讲", "八卦与旁证"]
    available_cats = [cat for cat in display_categories if cat in categories]
    tab_names.extend(available_cats)

    # 添加模式特定分类
    mode_cats = [cat for cat in categories if cat not in display_categories and cat != "低质量隐藏"]
    tab_names.extend(mode_cats)

tabs = st.tabs(tab_names)

# 全部来源 tab
with tabs[0]:
    _render_source_list(filtered, client, show_origin=_is_report_ingestion, key_prefix="all_")

# 分类 tabs
if _is_report_ingestion:
    for idx, cat_name in enumerate(available_cats, 1):
        with tabs[idx]:
            cat_items = ri_categories.get(cat_name, [])
            if not cat_items:
                st.info(f"「{cat_name}」暂无内容。")
            else:
                _render_source_list(cat_items, client, show_origin=True, key_prefix=f"cat{idx}_")
else:
    for idx, cat_name in enumerate(tab_names[1:], 1):
        with tabs[idx]:
            cat_items = categories.get(cat_name, [])
            if not cat_items:
                st.info(f"「{cat_name}」暂无内容。")
            else:
                _render_source_list(cat_items, client, key_prefix=f"cat{idx}_")

st.divider()

# === 研究索引预览 ===

with st.expander("📋 研究索引预览", expanded=False):
    _render_index_preview(task, all_items)

st.divider()

# === 事件日志 ===

with st.expander("📋 任务事件日志", expanded=False):
    try:
        events_data = client.get_events(task_id, limit=30)
        events = events_data.get("events", [])

        if events:
            for event in events:
                level = event.get("level", "info")
                icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(level, "ℹ️")
                time_str = event.get("created_at", "")[:19].replace("T", " ")
                st.caption(f"{icon} `{time_str}` **{event['event_type']}** — {event['message']}")
        else:
            st.info("暂无事件记录。")
    except Exception as e:
        st.warning(f"无法加载事件日志：{e}")
