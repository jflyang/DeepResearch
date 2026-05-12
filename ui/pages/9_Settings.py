"""Settings - 配置中心。

结构：
1. 顶部状态摘要卡片
2. Tabs: LLM / Search Providers / Obsidian / Service Priority / Diagnostics
"""

import streamlit as st
from ui.api_client import APIClient
from ui.styles import apply_global_styles
from ui.components.layout import render_page_header, render_section
from ui.pages._settings_helpers import (
    build_service_display_state,
    get_provider_card_status,
    mask_api_key_status,
)

apply_global_styles()
render_page_header("Settings", "配置 LLM、搜索 Provider、Obsidian Vault、服务优先级与运行策略。")

client = APIClient()

# === 连接检查 ===

try:
    health = client.health()
except Exception as e:
    st.error(f"无法连接后端 API：{e}")
    st.info("请确保后端已启动：`make api`")
    st.stop()


# ============================================================
# 一、顶部状态摘要
# ============================================================

try:
    priority_config = client.get_service_priority()
except Exception:
    priority_config = {"llm": {}, "search_policy": {}}

llm_config = priority_config.get("llm", {})
current_active = llm_config.get("active_provider", "deepseek")

try:
    obsidian_config = client.get_obsidian_settings()
    obs_ok = obsidian_config.get("configured") and obsidian_config.get("exists") and obsidian_config.get("writable")
except Exception:
    obsidian_config = {}
    obs_ok = False

ACTIVE_LABELS = {
    "deepseek": "DeepSeek", "ollama_lan": "Ollama", "openai": "OpenAI",
    "openai_compatible": "OpenAI-Compat", "mock_llm": "Mock",
}

sp_config = priority_config.get("search_policy", {})
search_mode = sp_config.get("mode", "free_first")

s_col1, s_col2, s_col3, s_col4 = st.columns(4)
s_col1.metric("LLM", ACTIVE_LABELS.get(current_active, current_active))
s_col2.metric("Search", search_mode)
s_col3.metric("Obsidian", "✅ 可用" if obs_ok else "⚠️ 未配置")
s_col4.metric("API", "✅ 连接正常")


# ============================================================
# 二、配置 Tabs
# ============================================================

tab_llm, tab_search, tab_obsidian, tab_priority, tab_diag = st.tabs(
    ["LLM", "Search Providers", "Obsidian", "Service Priority", "Diagnostics"]
)


# --- LLM Tab ---
with tab_llm:
    render_section("LLM Provider 配置")

    llm_providers_cfg = llm_config.get("providers", {})
    ACTIVE_OPTIONS = ["deepseek", "ollama_lan", "openai", "openai_compatible", "mock_llm"]

    # Active provider
    with st.form("llm_priority_form"):
        active_choice = st.selectbox(
            "默认 LLM Provider",
            options=ACTIVE_OPTIONS,
            format_func=lambda x: ACTIVE_LABELS.get(x, x),
            index=ACTIVE_OPTIONS.index(current_active) if current_active in ACTIVE_OPTIONS else 0,
        )

        st.markdown("**启用状态**")
        col1, col2 = st.columns(2)
        with col1:
            en_deepseek = st.checkbox("DeepSeek", value=llm_providers_cfg.get("deepseek", {}).get("enabled", current_active == "deepseek"))
            en_ollama = st.checkbox("Ollama", value=llm_providers_cfg.get("ollama_lan", {}).get("enabled", current_active == "ollama_lan"))
            en_mock = st.checkbox("Mock", value=llm_providers_cfg.get("mock_llm", {}).get("enabled", True))
        with col2:
            en_openai = st.checkbox("OpenAI", value=llm_providers_cfg.get("openai", {}).get("enabled", False))
            en_openai_compat = st.checkbox("OpenAI-Compatible", value=llm_providers_cfg.get("openai_compatible", {}).get("enabled", False))

        if st.form_submit_button("保存 LLM 配置", type="primary"):
            providers_payload = {
                "deepseek": {"enabled": en_deepseek},
                "ollama_lan": {"enabled": en_ollama},
                "openai": {"enabled": en_openai},
                "openai_compatible": {"enabled": en_openai_compat},
                "mock_llm": {"enabled": en_mock},
            }
            if not providers_payload.get(active_choice, {}).get("enabled", False):
                providers_payload[active_choice] = {"enabled": True}

            save_payload = {
                "llm": {"active_provider": active_choice, "provider_priority": ACTIVE_OPTIONS, "providers": providers_payload},
                "search_policy": priority_config.get("search_policy", {}),
            }
            try:
                result = client.save_service_priority(save_payload)
                if result.get("success"):
                    st.success("✅ 已保存")
                    st.rerun()
                else:
                    st.error(f"保存失败：{result.get('message', '')}")
            except Exception as e:
                st.error(f"保存失败：{e}")

    # Ollama 配置
    with st.expander("Ollama 局域网配置", expanded=False):
        try:
            ollama_config = client.get_ollama_settings()
        except Exception:
            ollama_config = {}

        _ollama_url = ollama_config.get("base_url", "") if ollama_config else ""
        _ollama_timeout = ollama_config.get("timeout_seconds", 120) if ollama_config else 120
        _ollama_model = ollama_config.get("default_model", "") if ollama_config else ""

        if ollama_config.get("configured"):
            st.caption(f"✅ 已配置 — {ollama_config.get('host', '')} / `{_ollama_model}`")
        else:
            st.caption("⚪ 未配置")

        with st.form("ollama_form"):
            ollama_url = st.text_input("服务器地址", value=_ollama_url, placeholder="http://192.168.1.50:11434")
            ollama_timeout = st.number_input("超时秒数", min_value=10, max_value=600, value=_ollama_timeout, step=10)
            ollama_form_ok = st.form_submit_button("应用地址")

        if ollama_form_ok and ollama_url:
            st.session_state["_ollama_url_pending"] = ollama_url
            st.session_state["_ollama_timeout_pending"] = ollama_timeout

        active_url = st.session_state.get("_ollama_url_pending", _ollama_url)
        if active_url:
            col_t, col_m = st.columns(2)
            with col_t:
                if st.button("测试连接", key="test_ollama"):
                    try:
                        result = client.test_ollama_connection(active_url)
                        if result.get("reachable"):
                            st.success(f"✅ 可达 ({result.get('latency_ms', '?')}ms)")
                        else:
                            st.error(f"❌ 不可达: {result.get('error', '')}")
                    except Exception as e:
                        st.error(f"失败: {e}")
            with col_m:
                if st.button("刷新模型列表", key="refresh_ollama_models"):
                    try:
                        models = client.list_ollama_models(active_url)
                        st.session_state["ollama_models"] = models
                    except Exception as e:
                        st.error(f"失败: {e}")

            models = st.session_state.get("ollama_models", [])
            if models:
                model_names = [m["name"] for m in models]
                default_idx = model_names.index(_ollama_model) if _ollama_model in model_names else 0
                selected_model = st.selectbox("默认模型", options=model_names, index=default_idx, key="ollama_model_sel")
                if st.button("保存 Ollama 配置", key="save_ollama", type="primary"):
                    try:
                        result = client.save_ollama_settings(
                            base_url=active_url, default_model=selected_model,
                            timeout_seconds=int(st.session_state.get("_ollama_timeout_pending", _ollama_timeout)),
                        )
                        if result.get("success"):
                            st.success("✅ 已保存")
                            st.session_state.pop("_ollama_url_pending", None)
                            st.session_state.pop("ollama_models", None)
                            st.rerun()
                    except Exception as e:
                        st.error(f"失败: {e}")

    # Cloud LLM 配置
    with st.expander("云端大模型 API", expanded=False):
        try:
            cloud_config = client.get_cloud_llm_settings()
        except Exception:
            cloud_config = {}

        key_status = mask_api_key_status(cloud_config)
        if cloud_config.get("enabled") and cloud_config.get("api_key_configured"):
            st.caption(f"✅ 已启用 — {cloud_config.get('provider', '')} / `{cloud_config.get('default_model', '')}`")
        elif cloud_config.get("enabled"):
            st.caption(f"⚠️ 已启用但缺少 API Key — {cloud_config.get('provider', '')}")
        else:
            st.caption("⚪ 未启用")

        PROVIDER_OPTIONS = ["deepseek", "openai", "openai_compatible"]
        _cloud_provider = cloud_config.get("provider", "deepseek")
        _cloud_base_url = cloud_config.get("base_url", "")
        _cloud_model = cloud_config.get("default_model", "")
        _cloud_timeout = cloud_config.get("timeout_seconds", 120)
        _cloud_enabled = cloud_config.get("enabled", False)

        with st.form("cloud_llm_form"):
            cloud_enabled = st.checkbox("启用云端 LLM", value=_cloud_enabled)
            cloud_provider = st.selectbox("Provider", options=PROVIDER_OPTIONS, index=PROVIDER_OPTIONS.index(_cloud_provider) if _cloud_provider in PROVIDER_OPTIONS else 0)
            cloud_api_key = st.text_input("API Key", type="password", placeholder=key_status["placeholder"])
            st.caption(key_status["help_text"])
            cloud_base_url = st.text_input("Base URL", value=_cloud_base_url, placeholder="https://api.deepseek.com")
            cloud_model = st.text_input("默认模型", value=_cloud_model, placeholder="deepseek-v4-flash")
            cloud_timeout = st.number_input("超时秒数", min_value=10, max_value=600, value=_cloud_timeout, step=10, key="cloud_timeout")

            if st.form_submit_button("保存云端 LLM", type="primary"):
                try:
                    result = client.save_cloud_llm_settings(
                        enabled=cloud_enabled, provider=cloud_provider, base_url=cloud_base_url,
                        api_key=cloud_api_key, default_model=cloud_model, timeout_seconds=int(cloud_timeout),
                    )
                    if result.get("success"):
                        st.success("✅ 已保存")
                        st.rerun()
                    else:
                        st.error(f"失败: {result.get('message', '')}")
                except Exception as e:
                    st.error(f"失败: {e}")


# --- Search Providers Tab ---
with tab_search:
    render_section("搜索 Provider 配置")

    sp_providers_cfg = sp_config.get("providers", {})
    sp_priority = sp_config.get("provider_priority", {})
    current_search_mode = sp_config.get("mode", "free_first")
    current_paid_enabled = sp_config.get("paid_providers_enabled", False)

    SEARCH_MODE_OPTIONS = ["free_first", "balanced", "paid_enhanced"]
    SEARCH_MODE_LABELS = {"free_first": "免费优先", "balanced": "均衡", "paid_enhanced": "付费增强"}

    with st.form("search_policy_form"):
        search_mode_sel = st.selectbox(
            "搜索模式", options=SEARCH_MODE_OPTIONS,
            format_func=lambda x: SEARCH_MODE_LABELS.get(x, x),
            index=SEARCH_MODE_OPTIONS.index(current_search_mode) if current_search_mode in SEARCH_MODE_OPTIONS else 0,
        )
        paid_enabled = st.checkbox("启用付费 Provider", value=current_paid_enabled)

        st.markdown("**Provider 启用状态**")
        col1, col2 = st.columns(2)
        with col1:
            en_searxng = st.checkbox("SearXNG", value=sp_providers_cfg.get("searxng", {}).get("enabled", False))
            en_wikipedia = st.checkbox("Wikipedia", value=sp_providers_cfg.get("wikipedia", {}).get("enabled", True))
            en_open_library = st.checkbox("Open Library", value=sp_providers_cfg.get("open_library", {}).get("enabled", True))
            en_crossref = st.checkbox("Crossref", value=sp_providers_cfg.get("crossref", {}).get("enabled", True))
        with col2:
            en_arxiv = st.checkbox("arXiv", value=sp_providers_cfg.get("arxiv", {}).get("enabled", True))
            en_google_books = st.checkbox("Google Books", value=sp_providers_cfg.get("google_books", {}).get("enabled", True))
            en_brave = st.checkbox("Brave", value=sp_providers_cfg.get("brave", {}).get("enabled", False))
            en_tavily = st.checkbox("Tavily", value=sp_providers_cfg.get("tavily", {}).get("enabled", True))

        TAVILY_MODE_OPTIONS = ["disabled", "fallback", "always"]
        current_tavily_mode = sp_providers_cfg.get("tavily", {}).get("mode", "fallback")
        tavily_mode = st.selectbox("Tavily 模式", options=TAVILY_MODE_OPTIONS, index=TAVILY_MODE_OPTIONS.index(current_tavily_mode) if current_tavily_mode in TAVILY_MODE_OPTIONS else 1)

        st.markdown("**搜索优先级**")
        default_web = sp_priority.get("web", ["searxng", "wikipedia", "brave", "tavily"])
        web_priority = st.multiselect("Web", options=["searxng", "wikipedia", "brave", "tavily"], default=[p for p in default_web if p in ["searxng", "wikipedia", "brave", "tavily"]])
        default_book = sp_priority.get("book", ["open_library", "google_books"])
        book_priority = st.multiselect("Book", options=["open_library", "google_books"], default=[p for p in default_book if p in ["open_library", "google_books"]])

        if st.form_submit_button("保存搜索配置", type="primary"):
            sp_providers_payload = {
                "searxng": {"enabled": en_searxng}, "wikipedia": {"enabled": en_wikipedia},
                "open_library": {"enabled": en_open_library}, "crossref": {"enabled": en_crossref},
                "arxiv": {"enabled": en_arxiv}, "google_books": {"enabled": en_google_books},
                "brave": {"enabled": en_brave}, "tavily": {"enabled": en_tavily, "mode": tavily_mode},
            }
            save_payload = {
                "llm": priority_config.get("llm", {}),
                "search_policy": {
                    "mode": search_mode_sel, "paid_providers_enabled": paid_enabled,
                    "provider_priority": {"web": web_priority, "book": book_priority, "academic": sp_priority.get("academic", [])},
                    "providers": sp_providers_payload,
                },
            }
            try:
                result = client.save_service_priority(save_payload)
                if result.get("success"):
                    st.success("✅ 已保存")
                    st.rerun()
                else:
                    st.error(f"失败: {result.get('message', '')}")
            except Exception as e:
                st.error(f"失败: {e}")

    # API Keys
    with st.expander("搜索 Provider API Key", expanded=False):
        try:
            search_keys_config = client.get_search_settings()
        except Exception:
            search_keys_config = {}

        if search_keys_config:
            tavily_cfg = search_keys_config.get("tavily", {})
            brave_cfg = search_keys_config.get("brave", {})
            tavily_key_status = mask_api_key_status(tavily_cfg)
            brave_key_status = mask_api_key_status(brave_cfg)

            with st.form("search_keys_form"):
                st.markdown("**Tavily**")
                tavily_key = st.text_input("Tavily API Key", type="password", placeholder=tavily_key_status["placeholder"])
                st.caption(tavily_key_status["help_text"])

                st.markdown("**Brave**")
                brave_key = st.text_input("Brave API Key", type="password", placeholder=brave_key_status["placeholder"])
                st.caption(brave_key_status["help_text"])

                if st.form_submit_button("保存 API Key", type="primary"):
                    payload = {"tavily": {"enabled": True, "api_key": tavily_key or None}, "brave": {"enabled": True, "api_key": brave_key or None}}
                    try:
                        result = client.save_search_settings(payload)
                        if result.get("success"):
                            st.success("✅ 已保存")
                            st.rerun()
                    except Exception as e:
                        st.error(f"失败: {e}")


# --- Obsidian Tab ---
with tab_obsidian:
    render_section("Obsidian Vault")
    st.caption("Vault 路径只需配置一次。新建研究任务会自动使用默认路径。")

    if obsidian_config.get("configured"):
        vault_path = obsidian_config.get("vault_path", "")
        if obs_ok:
            st.markdown(f"✅ Vault 已配置且可用: `{vault_path}`")
        elif obsidian_config.get("exists"):
            st.markdown(f"⚠️ 路径存在但不可写: `{vault_path}`")
        else:
            st.markdown(f"⚠️ 路径不存在: `{vault_path}`")
    else:
        st.markdown("⚪ Vault 未配置（导出功能不可用）")

    vault_input = st.text_input("Vault 路径", value=obsidian_config.get("vault_path", "") if obsidian_config else "", placeholder="/Users/you/Obsidian/Vault")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("测试路径", key="test_vault"):
            if vault_input:
                try:
                    result = client.test_obsidian_path(vault_input)
                    if result.get("exists") and result.get("writable"):
                        st.success("✅ 路径有效且可写")
                    else:
                        st.error(f"❌ {result.get('error', '路径无效')}")
                except Exception as e:
                    st.error(f"失败: {e}")
            else:
                st.warning("请先输入路径")
    with col2:
        if st.button("保存 Vault 路径", key="save_vault", type="primary"):
            if vault_input:
                try:
                    result = client.save_obsidian_settings(vault_input)
                    if result.get("success"):
                        st.success("✅ 已保存")
                        st.rerun()
                    else:
                        st.error(f"失败: {result.get('message', '')}")
                except Exception as e:
                    st.error(f"失败: {e}")
            else:
                st.warning("请先输入路径")


# --- Service Priority Tab ---
with tab_priority:
    render_section("服务优先级总览")

    st.markdown(f"**当前 LLM Provider**: {ACTIVE_LABELS.get(current_active, current_active)}")
    st.markdown(f"**搜索模式**: {SEARCH_MODE_LABELS.get(current_search_mode, current_search_mode)}")
    st.markdown(f"**付费 Provider**: {'启用' if current_paid_enabled else '未启用'}")

    st.caption("详细配置请在 LLM / Search Providers Tab 中修改。")


# --- Diagnostics Tab ---
with tab_diag:
    render_section("服务状态诊断")

    if st.button("刷新服务状态", key="refresh_services"):
        st.rerun()

    try:
        services = client.get_services()
    except Exception:
        services = []

    if services:
        for svc in services:
            display = build_service_display_state(svc)
            line = f"{display['icon']} **{display['name']}** ({display['type']}) — {display['label']}"
            if display["message"]:
                line += f" · {display['message']}"
            st.markdown(line)
    else:
        st.info("无法获取服务状态")

    with st.expander("配置说明", expanded=False):
        st.markdown("""
- 配置保存到 `config/runtime_settings.json`（优先级高于 `.env`）
- API Key 不会在页面明文显示，留空保留已有配置
- `runtime_settings.json` 已加入 `.gitignore`
- 也可以直接编辑 `.env` 文件配置
""")
