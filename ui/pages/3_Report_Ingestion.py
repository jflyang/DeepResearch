"""📥 导入外部研究报告 - 从 GPT / Deep Research / Perplexity / Claude 报告中提取来源。"""

import streamlit as st
from ui.api_client import APIClient

st.header("📥 导入外部研究报告")
st.caption("将 AI 生成的研究报告粘贴到此处，系统将自动提取引用来源并抓取正文。")

client = APIClient()


# === 纯函数（可测试） ===


def validate_report_input(topic: str, report_text: str) -> tuple[bool, str]:
    """验证输入，返回 (is_valid, error_message)。"""
    if not topic or not topic.strip():
        return False, "请输入研究主题"
    if not report_text or not report_text.strip():
        return False, "请粘贴研究报告内容"
    return True, ""


def build_report_options(
    extract_urls: bool,
    enrich_books: bool,
    enrich_papers: bool,
    analyze_documents: bool,
    export_to_obsidian: bool,
) -> dict:
    """构建 options 字典。"""
    return {
        "extract_urls": extract_urls,
        "enrich_books": enrich_books,
        "enrich_papers": enrich_papers,
        "analyze_documents": analyze_documents,
        "export_to_obsidian": export_to_obsidian,
    }


def format_reference_preview(parsed_response: dict) -> list[dict]:
    """格式化 references_preview 为表格数据。"""
    preview = parsed_response.get("references_preview", [])
    rows = []
    for ref in preview:
        ref_type = ref.get("type", "unknown")
        value = ref.get("value", "")
        hint = ref.get("title_hint") or ref.get("author_hint") or ref.get("doi_hint") or ""
        rows.append({"类型": ref_type, "内容": value, "提示": hint})
    return rows


# === 输入区域 ===

st.subheader("📝 输入")

topic = st.text_input(
    "研究主题",
    placeholder="例如：Tim Cook 的童年故事、量子计算最新进展",
    key="ri_topic",
)

report_source = st.selectbox(
    "报告来源",
    ["ChatGPT", "GPT Deep Research", "Perplexity", "Claude", "Gemini", "Other"],
    key="ri_source",
)

report_text = st.text_area(
    "报告内容",
    placeholder="将 AI 生成的研究报告粘贴到此处...",
    height=400,
    key="ri_report_text",
)

output_language = st.selectbox(
    "输出语言",
    ["zh", "en"],
    index=0,
    format_func=lambda x: "中文" if x == "zh" else "English",
    key="ri_language",
)

st.subheader("⚙️ 选项")

col1, col2 = st.columns(2)
with col1:
    extract_urls = st.checkbox("抓取报告中的网页链接", value=True, key="ri_extract_urls")
    enrich_books = st.checkbox("补充搜索报告中的书名", value=True, key="ri_enrich_books")
    enrich_papers = st.checkbox("补充搜索报告中的论文名", value=True, key="ri_enrich_papers")
with col2:
    analyze_documents = st.checkbox("提取正文后做中文摘要", value=True, key="ri_analyze")
    export_to_obsidian = st.checkbox("完成后自动导出到 Obsidian", value=False, key="ri_export")

st.divider()

# === 操作按钮 ===

col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)

# --- 创建导入任务 ---
with col_btn1:
    create_clicked = st.button("📋 创建导入任务", type="primary", key="ri_create")

if create_clicked:
    valid, error_msg = validate_report_input(topic, report_text)
    if not valid:
        st.error(error_msg)
    else:
        options = build_report_options(
            extract_urls, enrich_books, enrich_papers, analyze_documents, export_to_obsidian
        )
        with st.spinner("正在创建导入任务..."):
            try:
                result = client.create_report_import_task(
                    topic=topic.strip(),
                    report_text=report_text,
                    report_source=report_source,
                    output_language=output_language,
                    options=options,
                )
                task_id = result["task_id"]
                st.session_state["ri_task_id"] = task_id
                st.session_state["selected_task_id"] = task_id
                st.success(f"✅ 导入任务已创建：`{task_id}`")
            except Exception as e:
                st.error(f"创建任务失败：{e}")

# --- 解析报告 ---
with col_btn2:
    parse_clicked = st.button("🔍 解析报告", key="ri_parse")

if parse_clicked:
    task_id = st.session_state.get("ri_task_id")
    if not task_id:
        st.error("请先创建导入任务")
    else:
        with st.spinner("正在解析报告中的引用..."):
            try:
                parsed = client.parse_report_import_task(task_id)
                st.session_state["ri_parsed"] = parsed
                st.success("✅ 解析完成")
            except Exception as e:
                st.error(f"解析失败：{e}")

# --- 开始抓取与分析 ---
with col_btn3:
    run_clicked = st.button("🚀 开始抓取与分析", key="ri_run")

if run_clicked:
    task_id = st.session_state.get("ri_task_id")
    if not task_id:
        st.error("请先创建导入任务")
    else:
        with st.spinner("正在抓取网页和补充检索，请稍候..."):
            try:
                result = client.run_report_import_task(task_id)
                st.session_state["ri_result"] = result
                st.success("✅ 抓取与分析完成")
            except Exception as e:
                st.error(f"执行失败：{e}")

# --- 查看 Results ---
with col_btn4:
    if st.session_state.get("ri_task_id"):
        st.page_link("pages/2_Results.py", label="📊 查看 Results", icon="📊")

# === 解析预览 ===

parsed = st.session_state.get("ri_parsed")
if parsed:
    st.divider()
    st.subheader("🔍 解析预览")

    col1, col2, col3 = st.columns(3)
    col1.metric("URL 数量", parsed.get("url_count", 0))
    col2.metric("书名数量", parsed.get("book_count", 0))
    col3.metric("论文数量", parsed.get("paper_count", 0))

    preview_rows = format_reference_preview(parsed)
    if preview_rows:
        st.markdown("**引用预览：**")
        st.dataframe(preview_rows, use_container_width=True)

# === 运行结果 ===

ri_result = st.session_state.get("ri_result")
if ri_result:
    st.divider()
    st.subheader("✅ 导入结果")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("提取 URL 数", ri_result.get("extracted_document_count", 0))
    col2.metric("补充来源数", ri_result.get("enriched_source_count", 0))
    col3.metric("失败数", ri_result.get("failed_count", 0))
    col4.metric("总来源数", ri_result.get("source_count", 0))

    st.page_link("pages/2_Results.py", label="📊 前往 Results 查看详细结果", icon="📊")
