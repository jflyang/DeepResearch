"""研究结果工作台 - 查看分类结果、筛选排序、导出到 Obsidian。"""

import streamlit as st
from ui.api_client import APIClient


# === Helper Functions (must be defined before Streamlit execution) ===


def _render_source_list(items: list[dict], api_client: APIClient):
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
                    if st.button("📥 提取", key=f"extract_{item['id']}"):
                        with st.spinner("提取中..."):
                            try:
                                result = api_client.extract_source(item["id"])
                                if result.get("status") == "extracted":
                                    st.success("✅")
                                else:
                                    st.warning("失败")
                            except Exception as e:
                                st.error(f"失败: {e}")
                elif dl_status in ("extracted", "exported"):
                    st.caption(f"✅ {dl_status}")
                elif dl_status == "failed":
                    st.caption("❌ 失败")
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


def _render_llm_usage(task_id: str, api_client: APIClient):
    """渲染 LLM 使用情况区域。"""
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
    }

    for task_info in llm_tasks:
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
        elif status in ("skipped_disabled", "skipped_not_reached", "skipped_not_implemented"):
            reason = task_info.get("skipped_reason", "")
            line += f" — {reason}"
        st.markdown(line)

    rule_steps = llm_data.get("rule_only_steps", [])
    if rule_steps:
        st.caption(f"⚙️ 规则步骤（不使用 LLM）: {', '.join(rule_steps)}")


def _render_trace_view(task_id: str, api_client: APIClient):
    """渲染执行流程 / Trace 视图。"""
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

        line_parts = [f"{icon} **{step}**"]
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

    if st.button("🔄 刷新列表", key="refresh_history"):
        pass  # 触发 rerun

    # 获取任务列表
    try:
        status_filter = history_status if history_status != "全部" else None
        q_filter = history_q if history_q else None
        tasks_data = client.list_tasks(limit=30, status=status_filter, q=q_filter)
        history_tasks = tasks_data.get("items", [])
    except Exception:
        history_tasks = []

    if history_tasks:
        for ht in history_tasks:
            status_icon = {"completed": "✅", "running": "⏳", "pending": "🕐", "failed": "❌"}.get(ht["status"], "❓")
            topic_short = ht["topic"][:25] + ("..." if len(ht["topic"]) > 25 else "")
            source_info = f"{ht.get('source_count', 0)} sources"
            hq = ht.get("high_quality_count", 0)
            if hq:
                source_info += f" · {hq} S/A"
            export_badge = " · 📤" if ht.get("exported") else ""
            time_str = (ht.get("created_at") or "")[:10]

            label = f"{status_icon} **{topic_short}**\n{source_info}{export_badge} · {time_str}"

            if st.button(
                f"{status_icon} {topic_short}",
                key=f"hist_{ht['task_id']}",
                help=f"{ht['topic']} | {ht['status']} | {source_info}",
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
col2.metric("高质量 (S/A)", len(s_a_items))
col3.metric("图书资料", len(book_items))
col4.metric("已提取正文", len(extracted_items))
col5.metric("八卦线索", len(gossip_items))

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
        st.page_link("pages/3_Settings.py", label="前往 Settings 配置 Vault", icon="⚙️")
    else:
        st.info("📁 Obsidian Vault 未配置，导出功能不可用。请先到 Settings 配置默认 Obsidian Vault。")
        st.page_link("pages/3_Settings.py", label="前往 Settings 配置 Vault", icon="⚙️")

st.divider()

# === 筛选与排序 ===

st.subheader("🔍 筛选与排序")

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

with filter_col1:
    level_filter = st.selectbox(
        "来源等级",
        ["全部", "S", "A", "B", "C", "D"],
        index=0,
        key="level_filter",
    )

with filter_col2:
    type_options = ["全部"] + sorted(set(i["source_type"] for i in all_items))
    type_filter = st.selectbox("来源类型", type_options, index=0, key="type_filter")

with filter_col3:
    status_filter = st.selectbox(
        "下载状态",
        ["全部", "pending", "extracted", "exported", "failed"],
        index=0,
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

if level_filter != "全部":
    filtered = [i for i in filtered if i["source_level"] == level_filter]
if type_filter != "全部":
    filtered = [i for i in filtered if i["source_type"] == type_filter]
if status_filter != "全部":
    filtered = [i for i in filtered if i["download_status"] == status_filter]
if hide_low:
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
display_categories = ["必读资料", "一手资料", "深度报道", "图书资料", "采访与演讲", "八卦与旁证"]
available_cats = [cat for cat in display_categories if cat in categories]
tab_names.extend(available_cats)

# 添加模式特定分类
mode_cats = [cat for cat in categories if cat not in display_categories and cat != "低质量隐藏"]
tab_names.extend(mode_cats)

tabs = st.tabs(tab_names)

# 全部来源 tab
with tabs[0]:
    _render_source_list(filtered, client)

# 分类 tabs
for idx, cat_name in enumerate(tab_names[1:], 1):
    with tabs[idx]:
        cat_items = categories.get(cat_name, [])
        if not cat_items:
            st.info(f"「{cat_name}」暂无内容。")
        else:
            _render_source_list(cat_items, client)

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
