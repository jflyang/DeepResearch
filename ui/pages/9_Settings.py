"""设置页面 - 展示 LLM 与 API 服务配置状态，支持服务优先级手动配置。

所有配置从后端 API 读取（后端从 runtime_settings.json 加载）。
保存后 st.rerun() 确保页面重新从 API 获取最新状态。
Streamlit 页面按文件名前缀排序，9_ 确保 Settings 在最后。
"""

import streamlit as st
from ui.api_client import APIClient

st.header("⚙️ 设置与状态")

client = APIClient()

# === 连接检查 ===

try:
    health = client.health()
except Exception as e:
    st.error(f"无法连接后端 API：{e}")
    st.info("请确保后端已启动：`make api` 或 `uvicorn app.main:app --port 8000`")
    st.stop()

st.success("✅ 后端 API 连接正常")

st.divider()

# ============================================================
# 🤖 LLM Provider 优先级
# ============================================================

st.subheader("🤖 LLM Provider 优先级")

try:
    priority_config = client.get_service_priority()
except Exception as e:
    st.error(f"获取服务优先级配置失败：{e}")
    priority_config = {"llm": {}, "search_policy": {}}

llm_config = priority_config.get("llm", {})
current_active = llm_config.get("active_provider", "deepseek")
llm_providers_cfg = llm_config.get("providers", {})

ACTIVE_OPTIONS = ["deepseek", "ollama_lan", "openai", "openai_compatible", "mock_llm"]
ACTIVE_LABELS = {
    "deepseek": "DeepSeek",
    "ollama_lan": "Ollama（局域网）",
    "openai": "OpenAI",
    "openai_compatible": "OpenAI-Compatible",
    "mock_llm": "Mock（测试用）",
}

st.markdown(f"当前默认 Provider: **{ACTIVE_LABELS.get(current_active, current_active)}**")

with st.form("llm_priority_form"):
    active_choice = st.selectbox(
        "默认 LLM Provider",
        options=ACTIVE_OPTIONS,
        format_func=lambda x: ACTIVE_LABELS.get(x, x),
        index=ACTIVE_OPTIONS.index(current_active) if current_active in ACTIVE_OPTIONS else 0,
    )

    st.markdown("**启用状态：**")
    col1, col2 = st.columns(2)
    with col1:
        en_deepseek = st.checkbox("启用 DeepSeek", value=llm_providers_cfg.get("deepseek", {}).get("enabled", current_active == "deepseek"))
        en_ollama = st.checkbox("启用 Ollama", value=llm_providers_cfg.get("ollama_lan", {}).get("enabled", current_active == "ollama_lan"))
        en_mock = st.checkbox("启用 Mock", value=llm_providers_cfg.get("mock_llm", {}).get("enabled", True))
    with col2:
        en_openai = st.checkbox("启用 OpenAI", value=llm_providers_cfg.get("openai", {}).get("enabled", False))
        en_openai_compat = st.checkbox("启用 OpenAI-Compatible", value=llm_providers_cfg.get("openai_compatible", {}).get("enabled", False))

    llm_save_btn = st.form_submit_button("💾 保存 LLM 优先级")

if llm_save_btn:
    llm_providers_payload = {
        "deepseek": {"enabled": en_deepseek},
        "ollama_lan": {"enabled": en_ollama},
        "openai": {"enabled": en_openai},
        "openai_compatible": {"enabled": en_openai_compat},
        "mock_llm": {"enabled": en_mock},
    }
    # Ensure active provider is enabled
    if not llm_providers_payload.get(active_choice, {}).get("enabled", False):
        llm_providers_payload[active_choice] = {"enabled": True}

    save_payload = {
        "llm": {
            "active_provider": active_choice,
            "provider_priority": ACTIVE_OPTIONS,
            "providers": llm_providers_payload,
        },
        "search_policy": priority_config.get("search_policy", {
            "mode": "free_first",
            "paid_providers_enabled": False,
            "provider_priority": {},
            "providers": {},
        }),
    }
    with st.spinner("正在保存..."):
        try:
            result = client.save_service_priority(save_payload)
            if result.get("success"):
                st.success("✅ LLM 优先级已保存！")
                st.rerun()
            else:
                st.error(f"保存失败：{result.get('message', '未知错误')}")
        except Exception as e:
            st.error(f"保存请求失败：{e}")

st.divider()

# ============================================================
# 🔎 搜索 Provider 策略
# ============================================================

st.subheader("🔎 搜索 Provider 策略")

sp_config = priority_config.get("search_policy", {})
current_search_mode = sp_config.get("mode", "free_first")
current_paid_enabled = sp_config.get("paid_providers_enabled", False)
sp_providers_cfg = sp_config.get("providers", {})
sp_priority = sp_config.get("provider_priority", {})

SEARCH_MODE_OPTIONS = ["free_first", "balanced", "paid_enhanced"]
SEARCH_MODE_LABELS = {
    "free_first": "免费优先 (free_first)",
    "balanced": "均衡 (balanced)",
    "paid_enhanced": "付费增强 (paid_enhanced)",
}

TAVILY_MODE_OPTIONS = ["disabled", "fallback", "always"]
TAVILY_MODE_LABELS = {
    "disabled": "禁用",
    "fallback": "Fallback（免费不足时使用）",
    "always": "始终使用",
}

with st.form("search_policy_form"):
    search_mode = st.selectbox(
        "搜索模式",
        options=SEARCH_MODE_OPTIONS,
        format_func=lambda x: SEARCH_MODE_LABELS.get(x, x),
        index=SEARCH_MODE_OPTIONS.index(current_search_mode) if current_search_mode in SEARCH_MODE_OPTIONS else 0,
    )

    paid_enabled = st.checkbox("启用付费搜索 Provider", value=current_paid_enabled)

    st.markdown("**Provider 启用状态：**")
    col1, col2 = st.columns(2)
    with col1:
        en_searxng = st.checkbox("SearXNG", value=sp_providers_cfg.get("searxng", {}).get("enabled", False))
        en_wikipedia = st.checkbox("Wikipedia", value=sp_providers_cfg.get("wikipedia", {}).get("enabled", True))
        en_open_library = st.checkbox("Open Library", value=sp_providers_cfg.get("open_library", {}).get("enabled", True))
        en_crossref = st.checkbox("Crossref", value=sp_providers_cfg.get("crossref", {}).get("enabled", True))
    with col2:
        en_arxiv = st.checkbox("arXiv", value=sp_providers_cfg.get("arxiv", {}).get("enabled", True))
        en_google_books = st.checkbox("Google Books", value=sp_providers_cfg.get("google_books", {}).get("enabled", True))
        gb_public = st.checkbox("Google Books Public Mode", value=sp_providers_cfg.get("google_books", {}).get("public_mode", True))
        en_brave = st.checkbox("Brave", value=sp_providers_cfg.get("brave", {}).get("enabled", False))

    st.markdown("---")
    current_tavily_mode = sp_providers_cfg.get("tavily", {}).get("mode", "fallback")
    en_tavily = st.checkbox("Tavily", value=sp_providers_cfg.get("tavily", {}).get("enabled", True))
    tavily_mode = st.selectbox(
        "Tavily 使用模式",
        options=TAVILY_MODE_OPTIONS,
        format_func=lambda x: TAVILY_MODE_LABELS.get(x, x),
        index=TAVILY_MODE_OPTIONS.index(current_tavily_mode) if current_tavily_mode in TAVILY_MODE_OPTIONS else 1,
    )

    st.markdown("---")
    st.markdown("**Web 搜索优先级**（顺序即优先级）")
    default_web = sp_priority.get("web", ["searxng", "wikipedia", "brave", "tavily"])
    web_priority = st.multiselect(
        "Web 搜索顺序",
        options=["searxng", "wikipedia", "brave", "tavily"],
        default=[p for p in default_web if p in ["searxng", "wikipedia", "brave", "tavily"]],
    )

    st.markdown("**Book 搜索优先级**")
    default_book = sp_priority.get("book", ["open_library", "google_books"])
    book_priority = st.multiselect(
        "Book 搜索顺序",
        options=["open_library", "google_books"],
        default=[p for p in default_book if p in ["open_library", "google_books"]],
    )

    st.markdown("**Academic 搜索优先级**")
    default_academic = sp_priority.get("academic", ["crossref", "arxiv", "wikipedia"])
    academic_priority = st.multiselect(
        "Academic 搜索顺序",
        options=["crossref", "arxiv", "wikipedia"],
        default=[p for p in default_academic if p in ["crossref", "arxiv", "wikipedia"]],
    )

    search_save_btn = st.form_submit_button("💾 保存搜索策略")

if search_save_btn:
    sp_providers_payload = {
        "searxng": {"enabled": en_searxng},
        "wikipedia": {"enabled": en_wikipedia},
        "open_library": {"enabled": en_open_library},
        "crossref": {"enabled": en_crossref},
        "arxiv": {"enabled": en_arxiv},
        "google_books": {"enabled": en_google_books, "public_mode": gb_public},
        "brave": {"enabled": en_brave},
        "tavily": {"enabled": en_tavily, "mode": tavily_mode},
    }
    sp_priority_payload = {
        "web": web_priority,
        "book": book_priority,
        "academic": academic_priority,
        "general": ["searxng", "wikipedia", "open_library", "crossref", "tavily"],
    }

    save_payload = {
        "llm": priority_config.get("llm", {
            "active_provider": current_active,
            "provider_priority": ACTIVE_OPTIONS,
            "providers": {},
        }),
        "search_policy": {
            "mode": search_mode,
            "paid_providers_enabled": paid_enabled,
            "provider_priority": sp_priority_payload,
            "providers": sp_providers_payload,
        },
    }
    with st.spinner("正在保存..."):
        try:
            result = client.save_service_priority(save_payload)
            if result.get("success"):
                st.success("✅ 搜索策略已保存！")
                st.rerun()
            else:
                st.error(f"保存失败：{result.get('message', '未知错误')}")
        except Exception as e:
            st.error(f"保存请求失败：{e}")

st.divider()

# ============================================================
# 🦙 局域网 Ollama 配置
# ============================================================

st.subheader("🦙 局域网 Ollama 配置")

try:
    ollama_config = client.get_ollama_settings()
except Exception as e:
    st.error(f"获取 Ollama 配置失败：{e}")
    ollama_config = {}

if ollama_config:
    if ollama_config.get("configured"):
        st.markdown(f"✅ 当前已配置 — **{ollama_config.get('host', '')}** / 模型: `{ollama_config.get('default_model', 'N/A')}`")
    else:
        st.markdown("⚠️ Ollama 未配置")

_ollama_base_url = ollama_config.get("base_url", "") if ollama_config else ""
_ollama_timeout = ollama_config.get("timeout_seconds", 120) if ollama_config else 120
_ollama_model = ollama_config.get("default_model", "") if ollama_config else ""

with st.form("ollama_config_form"):
    ollama_url = st.text_input(
        "Ollama 服务器地址",
        value=_ollama_base_url,
        placeholder="http://192.168.1.50:11434",
        help="局域网 Ollama 服务的完整地址",
    )
    ollama_timeout = st.number_input(
        "超时秒数", min_value=10, max_value=600, value=_ollama_timeout, step=10,
    )
    form_submitted = st.form_submit_button("应用地址设置")

if form_submitted and ollama_url:
    st.session_state["_ollama_url_pending"] = ollama_url
    st.session_state["_ollama_timeout_pending"] = ollama_timeout

active_url = st.session_state.get("_ollama_url_pending", _ollama_base_url)
active_timeout = st.session_state.get("_ollama_timeout_pending", _ollama_timeout)

if active_url:
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 测试 Ollama 连接"):
            with st.spinner("正在测试..."):
                try:
                    result = client.test_ollama_connection(active_url)
                    if result.get("reachable"):
                        st.success(f"✅ Ollama 可达（延迟 {result.get('latency_ms', '?')}ms）")
                    else:
                        st.error(f"❌ Ollama 不可达：{result.get('error', '未知错误')}")
                except Exception as e:
                    st.error(f"测试请求失败：{e}")
    with col2:
        if st.button("🔄 刷新 Ollama 模型列表"):
            with st.spinner("正在获取模型列表..."):
                try:
                    models = client.list_ollama_models(active_url)
                    st.session_state["ollama_models"] = models
                except Exception as e:
                    st.error(f"获取模型列表失败：{e}")
                    st.session_state["ollama_models"] = []

    models = st.session_state.get("ollama_models", [])
    if models:
        model_names = [m["name"] for m in models]
        default_idx = model_names.index(_ollama_model) if _ollama_model in model_names else 0
        selected_model = st.selectbox("默认模型（Ollama）", options=model_names, index=default_idx, key="ollama_model_select")

        if st.button("💾 保存 Ollama 配置"):
            with st.spinner("正在保存..."):
                try:
                    result = client.save_ollama_settings(
                        base_url=active_url, default_model=selected_model, timeout_seconds=int(active_timeout),
                    )
                    if result.get("success"):
                        st.success("✅ Ollama 配置已保存！")
                        st.session_state.pop("_ollama_url_pending", None)
                        st.session_state.pop("_ollama_timeout_pending", None)
                        st.session_state.pop("ollama_models", None)
                        st.rerun()
                    else:
                        st.error(f"保存失败：{result.get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"保存请求失败：{e}")

st.divider()

# ============================================================
# ☁️ 云端大模型 API
# ============================================================

st.subheader("☁️ 云端大模型 API")

try:
    cloud_config = client.get_cloud_llm_settings()
except Exception as e:
    st.error(f"获取云端 LLM 配置失败：{e}")
    cloud_config = {}

if cloud_config:
    if cloud_config.get("enabled") and cloud_config.get("api_key_configured"):
        st.markdown(f"✅ 已启用 — **{cloud_config.get('provider', '')}** / 模型: `{cloud_config.get('default_model', 'N/A')}`")
    elif cloud_config.get("enabled"):
        st.markdown(f"⚠️ 已启用 — **{cloud_config.get('provider', '')}** / API Key 未配置")
    else:
        st.markdown("⚪ 云端 LLM 未启用")

PROVIDER_OPTIONS = ["deepseek", "openai", "openai_compatible"]
PROVIDER_LABELS_CLOUD = {"deepseek": "DeepSeek", "openai": "OpenAI", "openai_compatible": "OpenAI-Compatible"}

_cloud_provider = cloud_config.get("provider", "deepseek")
_cloud_base_url = cloud_config.get("base_url", "")
_cloud_model = cloud_config.get("default_model", "")
_cloud_timeout = cloud_config.get("timeout_seconds", 120)
_cloud_enabled = cloud_config.get("enabled", False)
_cloud_api_key_configured = cloud_config.get("api_key_configured", False)

with st.form("cloud_llm_form"):
    cloud_enabled = st.checkbox("启用云端 LLM", value=_cloud_enabled)
    provider_idx = PROVIDER_OPTIONS.index(_cloud_provider) if _cloud_provider in PROVIDER_OPTIONS else 0
    cloud_provider = st.selectbox("Provider", options=PROVIDER_OPTIONS, format_func=lambda x: PROVIDER_LABELS_CLOUD.get(x, x), index=provider_idx)
    cloud_api_key = st.text_input("API Key", type="password", placeholder="已配置，如需修改请重新输入" if _cloud_api_key_configured else "sk-...", help="留空保留已有 Key")
    if _cloud_api_key_configured:
        st.caption("✅ API Key 已配置（留空保留，重新输入可更换）")
    cloud_base_url = st.text_input("Base URL", value=_cloud_base_url, placeholder="https://api.deepseek.com")
    cloud_model = st.text_input("默认模型", value=_cloud_model, placeholder="deepseek-v4-flash / gpt-4.1-mini")
    cloud_timeout = st.number_input("超时秒数", min_value=10, max_value=600, value=_cloud_timeout, step=10, key="cloud_timeout_input")
    cloud_form_submitted = st.form_submit_button("💾 保存云端 LLM 配置")

if cloud_form_submitted:
    with st.spinner("正在保存..."):
        try:
            result = client.save_cloud_llm_settings(
                enabled=cloud_enabled, provider=cloud_provider, base_url=cloud_base_url,
                api_key=cloud_api_key, default_model=cloud_model, timeout_seconds=int(cloud_timeout),
            )
            if result.get("success"):
                st.success("✅ 云端 LLM 配置已保存！")
                st.rerun()
            else:
                st.error(f"保存失败：{result.get('message', '未知错误')}")
        except Exception as e:
            st.error(f"保存请求失败：{e}")

st.divider()

# ============================================================
# 🔌 搜索 Provider API Key 配置
# ============================================================

st.subheader("🔌 搜索 Provider API Key")

try:
    search_config = client.get_search_settings()
except Exception as e:
    st.error(f"获取搜索配置失败：{e}")
    search_config = {}

if search_config:
    tavily = search_config.get("tavily", {})
    brave = search_config.get("brave", {})

    with st.form("search_keys_form"):
        st.markdown("**Tavily**")
        tavily_key = st.text_input(
            "Tavily API Key", type="password",
            placeholder="已配置" if tavily.get("api_key_configured") else "tvly-...",
            help="留空保留已有 Key",
        )
        if tavily.get("api_key_configured"):
            st.caption("✅ Tavily Key 已配置")

        st.markdown("**Brave**")
        brave_key = st.text_input(
            "Brave API Key", type="password",
            placeholder="已配置" if brave.get("api_key_configured") else "BSA-...",
            help="留空保留已有 Key",
        )
        if brave.get("api_key_configured"):
            st.caption("✅ Brave Key 已配置")

        keys_save_btn = st.form_submit_button("💾 保存 API Key")

    if keys_save_btn:
        payload = {
            "tavily": {"enabled": True, "api_key": tavily_key or None},
            "brave": {"enabled": True, "api_key": brave_key or None},
        }
        with st.spinner("正在保存..."):
            try:
                result = client.save_search_settings(payload)
                if result.get("success"):
                    st.success("✅ API Key 已保存！")
                    st.rerun()
                else:
                    st.error(f"保存失败：{result.get('message', '未知错误')}")
            except Exception as e:
                st.error(f"保存请求失败：{e}")

st.divider()

# ============================================================
# 📁 Obsidian Vault 配置
# ============================================================

st.subheader("📁 Obsidian Vault")

st.caption("Vault 路径只需配置一次。新建研究任务会自动使用这里保存的默认路径。")

try:
    obsidian_config = client.get_obsidian_settings()
except Exception as e:
    st.error(f"获取 Obsidian 配置失败：{e}")
    obsidian_config = {}

if obsidian_config:
    if obsidian_config.get("configured"):
        vault_path = obsidian_config.get("vault_path", "")
        exists = obsidian_config.get("exists", False)
        writable = obsidian_config.get("writable", False)
        if exists and writable:
            st.markdown(f"✅ Vault 已配置且可用: `{vault_path}`")
        elif exists:
            st.markdown(f"⚠️ Vault 路径存在但不可写: `{vault_path}`")
        else:
            st.markdown(f"⚠️ Vault 路径不存在: `{vault_path}`")
    else:
        st.markdown("⚠️ Vault 路径未配置（导出功能不可用）")

vault_input = st.text_input(
    "Vault 路径",
    value=obsidian_config.get("vault_path", "") if obsidian_config else "",
    placeholder="/Users/you/Obsidian/ResearchVault",
)

col1, col2 = st.columns(2)
with col1:
    if st.button("🔍 测试路径"):
        if vault_input:
            with st.spinner("正在测试..."):
                try:
                    result = client.test_obsidian_path(vault_input)
                    if result.get("exists") and result.get("writable"):
                        st.success("✅ 路径有效且可写")
                    else:
                        st.error(f"❌ {result.get('error', '路径无效')}")
                except Exception as e:
                    st.error(f"测试失败：{e}")
        else:
            st.warning("请先输入路径")
with col2:
    if st.button("💾 保存 Vault 路径"):
        if vault_input:
            with st.spinner("正在保存..."):
                try:
                    result = client.save_obsidian_settings(vault_input)
                    if result.get("success"):
                        st.success("✅ Vault 路径已保存！")
                        st.rerun()
                    else:
                        st.error(f"保存失败：{result.get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"保存请求失败：{e}")
        else:
            st.warning("请先输入路径")

st.divider()

# ============================================================
# 📋 全部服务状态详情
# ============================================================

with st.expander("📋 全部服务状态详情", expanded=False):
    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 刷新服务状态", key="refresh_services_btn"):
            st.rerun()

    try:
        services = client.get_services()
    except Exception as e:
        st.error(f"获取服务列表失败：{e}")
        services = []

    if services:
        for svc in services:
            name = svc.get("name", "?")
            svc_type = svc.get("type", "?")
            severity = svc.get("severity", "inactive")
            active = svc.get("active", False)
            message = svc.get("message") or svc.get("note", "")

            # Icon based on severity (not enabled/configured)
            if severity == "ok":
                icon = "✅"
            elif severity == "warning":
                icon = "⚠️"
            elif severity == "inactive":
                icon = "⚪"
            elif severity == "error":
                icon = "❌"
            else:
                icon = "⚪"

            line = f"{icon} **{name}** ({svc_type})"
            if message:
                line += f" — {message}"
            st.markdown(line)

st.divider()

# === 配置说明 ===

st.subheader("📝 配置说明")
st.markdown("""
- 配置保存到 `config/runtime_settings.json`（优先级高于 `.env`）
- API Key 不会在页面明文显示，留空保留已有配置
- `runtime_settings.json` 已加入 `.gitignore`，不会提交到代码仓库
- 也可以直接编辑 `.env` 文件配置
- Streamlit 页面按文件名前缀排序（1\_, 2\_, 3\_, ... 9\_），Settings 使用 9\\_ 确保在最后
""")
