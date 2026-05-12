"""设置页面 - 展示 LLM 与 API 服务配置状态。"""

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

# === 局域网 Ollama 配置 ===

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

with st.form("ollama_config_form"):
    current_url = ollama_config.get("base_url", "") if ollama_config else ""
    current_timeout = ollama_config.get("timeout_seconds", 120) if ollama_config else 120

    ollama_url = st.text_input(
        "Ollama 服务器地址",
        value=current_url,
        placeholder="http://192.168.1.50:11434",
        help="局域网 Ollama 服务的完整地址",
    )
    ollama_timeout = st.number_input(
        "超时秒数",
        min_value=10,
        max_value=600,
        value=current_timeout,
        step=10,
    )
    form_submitted = st.form_submit_button("应用地址设置")

if form_submitted and ollama_url:
    st.session_state["ollama_url"] = ollama_url
    st.session_state["ollama_timeout"] = ollama_timeout

active_url = st.session_state.get("ollama_url", current_url)
active_timeout = st.session_state.get("ollama_timeout", current_timeout)

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
        current_model = ollama_config.get("default_model", "") if ollama_config else ""
        default_idx = 0
        if current_model in model_names:
            default_idx = model_names.index(current_model)

        selected_model = st.selectbox(
            "默认模型（Ollama）",
            options=model_names,
            index=default_idx,
            key="ollama_model_select",
        )

        for m in models:
            if m["name"] == selected_model:
                size_gb = m.get("size", 0) / (1024 ** 3)
                st.caption(f"大小: {size_gb:.1f} GB | 更新: {m.get('modified_at', 'N/A')[:10]}")
                break

        if st.button("💾 保存 Ollama 配置"):
            with st.spinner("正在保存..."):
                try:
                    result = client.save_ollama_settings(
                        base_url=active_url,
                        default_model=selected_model,
                        timeout_seconds=int(active_timeout),
                    )
                    if result.get("success"):
                        st.success("✅ Ollama 配置已保存！")
                    else:
                        st.error(f"保存失败：{result.get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"保存请求失败：{e}")
    elif st.session_state.get("ollama_models") is not None:
        st.info("该 Ollama 服务暂未发现模型，请确认服务器已 pull 模型。")
else:
    st.caption("请输入 Ollama 服务器地址后点击「应用地址设置」。")

st.divider()

# === 云端大模型 API ===

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
        st.markdown("❌ 云端 LLM 未启用")

# 云端 LLM 配置表单
PROVIDER_OPTIONS = ["deepseek", "openai", "openai_compatible"]
PROVIDER_LABELS = {"deepseek": "DeepSeek", "openai": "OpenAI", "openai_compatible": "OpenAI-Compatible"}
DEFAULT_URLS = {
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "openai_compatible": "",
}

with st.form("cloud_llm_form"):
    cloud_enabled = st.checkbox(
        "启用云端 LLM",
        value=cloud_config.get("enabled", False),
    )

    current_provider = cloud_config.get("provider", "deepseek")
    provider_idx = PROVIDER_OPTIONS.index(current_provider) if current_provider in PROVIDER_OPTIONS else 0

    cloud_provider = st.selectbox(
        "Provider",
        options=PROVIDER_OPTIONS,
        format_func=lambda x: PROVIDER_LABELS.get(x, x),
        index=provider_idx,
    )

    cloud_api_key = st.text_input(
        "API Key",
        type="password",
        placeholder="sk-...",
        help="API Key 仅保存在本地 runtime_settings.json，不会上传或显示明文",
    )
    if cloud_config.get("api_key_configured"):
        st.caption("✅ API Key 已配置（如需更换请重新输入）")

    cloud_base_url = st.text_input(
        "Base URL",
        value=cloud_config.get("base_url", DEFAULT_URLS.get(current_provider, "")),
        placeholder="https://api.deepseek.com/v1",
    )

    cloud_model = st.text_input(
        "默认模型",
        value=cloud_config.get("default_model", ""),
        placeholder="deepseek-chat / gpt-4.1-mini",
    )

    cloud_timeout = st.number_input(
        "超时秒数",
        min_value=10,
        max_value=600,
        value=cloud_config.get("timeout_seconds", 120),
        step=10,
        key="cloud_timeout",
    )

    cloud_form_submitted = st.form_submit_button("应用云端设置")

if cloud_form_submitted:
    st.session_state["cloud_provider"] = cloud_provider
    st.session_state["cloud_base_url"] = cloud_base_url
    st.session_state["cloud_api_key"] = cloud_api_key
    st.session_state["cloud_model"] = cloud_model
    st.session_state["cloud_timeout"] = cloud_timeout
    st.session_state["cloud_enabled"] = cloud_enabled

# 操作按钮
active_cloud_provider = st.session_state.get("cloud_provider", cloud_config.get("provider", "deepseek"))
active_cloud_url = st.session_state.get("cloud_base_url", cloud_config.get("base_url", ""))
active_cloud_key = st.session_state.get("cloud_api_key", "")
active_cloud_model = st.session_state.get("cloud_model", cloud_config.get("default_model", ""))
active_cloud_timeout = st.session_state.get("cloud_timeout", cloud_config.get("timeout_seconds", 120))
active_cloud_enabled = st.session_state.get("cloud_enabled", cloud_config.get("enabled", False))

if active_cloud_url and active_cloud_key:
    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔍 测试云端连接"):
            with st.spinner("正在测试..."):
                try:
                    result = client.test_cloud_llm_connection(
                        provider=active_cloud_provider,
                        base_url=active_cloud_url,
                        api_key=active_cloud_key,
                        model=active_cloud_model or "test",
                    )
                    if result.get("reachable"):
                        st.success(f"✅ 云端 LLM 可达（延迟 {result.get('latency_ms', '?')}ms）")
                    else:
                        st.error(f"❌ 不可达：{result.get('error', '未知错误')}")
                except Exception as e:
                    st.error(f"测试请求失败：{e}")

    with col2:
        if st.button("🔄 获取模型列表"):
            with st.spinner("正在获取..."):
                try:
                    result = client.list_cloud_llm_models(
                        provider=active_cloud_provider,
                        base_url=active_cloud_url,
                        api_key=active_cloud_key,
                    )
                    st.session_state["cloud_models"] = result.get("models", [])
                    if result.get("note"):
                        st.info(result["note"])
                except Exception as e:
                    st.error(f"获取模型列表失败：{e}")
                    st.session_state["cloud_models"] = []

    # 显示模型列表（如果有）
    cloud_models = st.session_state.get("cloud_models", [])
    if cloud_models:
        model_ids = [m["id"] for m in cloud_models]
        selected_cloud_model = st.selectbox(
            "选择模型",
            options=model_ids,
            index=model_ids.index(active_cloud_model) if active_cloud_model in model_ids else 0,
            key="cloud_model_select",
        )
        st.session_state["cloud_model"] = selected_cloud_model

    # 保存按钮
    if st.button("💾 保存云端 LLM 配置"):
        final_model = st.session_state.get("cloud_model", active_cloud_model)
        with st.spinner("正在保存..."):
            try:
                result = client.save_cloud_llm_settings(
                    enabled=active_cloud_enabled,
                    provider=active_cloud_provider,
                    base_url=active_cloud_url,
                    api_key=active_cloud_key,
                    default_model=final_model,
                    timeout_seconds=int(active_cloud_timeout),
                )
                if result.get("success"):
                    st.success("✅ 云端 LLM 配置已保存！")
                else:
                    st.error(f"保存失败：{result.get('message', '未知错误')}")
            except Exception as e:
                st.error(f"保存请求失败：{e}")

elif active_cloud_url and not active_cloud_key:
    st.caption("请输入 API Key 后进行测试和保存。")
else:
    st.caption("请填写 Base URL 和 API Key 后点击「应用云端设置」。")

st.divider()

# === 当前默认 LLM Provider ===

st.subheader("🎯 当前默认 LLM Provider")

try:
    llm_config = client.get_llm_config()
    current_active = llm_config.get("active_provider", "ollama_lan")
except Exception:
    current_active = "ollama_lan"

ACTIVE_OPTIONS = ["ollama_lan", "deepseek", "openai", "openai_compatible"]
ACTIVE_LABELS = {
    "ollama_lan": "Ollama（局域网）",
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "openai_compatible": "OpenAI-Compatible",
}

st.markdown(f"当前默认: **{ACTIVE_LABELS.get(current_active, current_active)}**")

active_choice = st.selectbox(
    "切换默认 LLM Provider",
    options=ACTIVE_OPTIONS,
    format_func=lambda x: ACTIVE_LABELS.get(x, x),
    index=ACTIVE_OPTIONS.index(current_active) if current_active in ACTIVE_OPTIONS else 0,
    key="active_provider_select",
)

if st.button("🔀 设置为默认 LLM"):
    with st.spinner("正在切换..."):
        try:
            result = client.set_active_llm_provider(active_choice)
            if result.get("success"):
                st.success(f"✅ 已切换为 {ACTIVE_LABELS.get(active_choice, active_choice)}")
            else:
                st.error("切换失败")
        except Exception as e:
            st.error(f"切换请求失败：{e}")

st.divider()

# === 搜索 Provider 配置 ===

st.subheader("🔌 搜索 Provider 配置")

try:
    search_config = client.get_search_settings()
except Exception as e:
    st.error(f"获取搜索配置失败：{e}")
    search_config = {}

if search_config:
    # 状态显示
    tavily = search_config.get("tavily", {})
    brave = search_config.get("brave", {})
    gb = search_config.get("google_books", {})

    if tavily.get("api_key_configured"):
        st.markdown("✅ **Tavily** — API Key 已配置")
    elif tavily.get("enabled"):
        st.markdown("⚠️ **Tavily** — 已启用，但 API Key 未配置")
    else:
        st.markdown("❌ **Tavily** — 已禁用")

    if brave.get("api_key_configured"):
        st.markdown("✅ **Brave** — API Key 已配置")
    elif brave.get("enabled"):
        st.markdown("⚠️ **Brave** — 已启用，但 API Key 未配置")
    else:
        st.markdown("❌ **Brave** — 已禁用")

    gb_mode = gb.get("mode", "public")
    if gb_mode == "public":
        st.markdown("✅ **Google Books** — Public Mode")
    elif gb.get("api_key_configured"):
        st.markdown("✅ **Google Books** — Authenticated Mode")
    else:
        st.markdown("❌ **Google Books** — 已禁用")

    st.markdown("")

    # 编辑表单
    with st.form("search_config_form"):
        st.markdown("**编辑搜索配置**")

        tavily_enabled = st.checkbox("启用 Tavily", value=tavily.get("enabled", True))
        tavily_key = st.text_input(
            "Tavily API Key",
            type="password",
            placeholder="tvly-...",
            help="留空不修改已有 Key",
        )
        if tavily.get("api_key_configured"):
            st.caption("✅ Tavily Key 已配置（重新输入可更换）")

        st.markdown("---")
        brave_enabled = st.checkbox("启用 Brave", value=brave.get("enabled", True))
        brave_key = st.text_input(
            "Brave API Key",
            type="password",
            placeholder="BSA-...",
            help="留空不修改已有 Key",
        )
        if brave.get("api_key_configured"):
            st.caption("✅ Brave Key 已配置（重新输入可更换）")

        st.markdown("---")
        gb_enabled = st.checkbox("启用 Google Books", value=gb.get("enabled", True))
        gb_public = st.checkbox(
            "Google Books Public Mode（无需 API Key）",
            value=(gb_mode == "public"),
        )
        gb_key = st.text_input(
            "Google Books API Key（可选）",
            type="password",
            placeholder="AIza-...",
            help="Public Mode 下无需填写",
        )

        search_save_btn = st.form_submit_button("💾 保存搜索配置")

    if search_save_btn:
        payload = {
            "tavily": {"enabled": tavily_enabled, "api_key": tavily_key or None},
            "brave": {"enabled": brave_enabled, "api_key": brave_key or None},
            "google_books": {"enabled": gb_enabled, "api_key": gb_key or None, "public_mode": gb_public},
        }
        with st.spinner("正在保存..."):
            try:
                result = client.save_search_settings(payload)
                if result.get("success"):
                    st.success("✅ 搜索配置已保存！")
                else:
                    st.error(f"保存失败：{result.get('message', '未知错误')}")
            except Exception as e:
                st.error(f"保存请求失败：{e}")

st.divider()

# === Obsidian Vault 配置 ===

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

# Vault 路径编辑
vault_input = st.text_input(
    "Vault 路径",
    value=obsidian_config.get("vault_path", "") if obsidian_config else "",
    placeholder="/Users/you/Obsidian/ResearchVault",
    help="Obsidian Vault 的本地路径",
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
                    else:
                        st.error(f"保存失败：{result.get('message', '未知错误')}")
                except Exception as e:
                    st.error(f"保存请求失败：{e}")
        else:
            st.warning("请先输入路径")

st.divider()

# === 全部服务状态 ===

with st.expander("📋 全部服务状态详情"):
    try:
        services = client.get_services()
    except Exception as e:
        st.error(f"获取服务列表失败：{e}")
        services = []

    if services:
        for svc in services:
            name = svc.get("name", "?")
            svc_type = svc.get("type", "?")
            enabled = svc.get("enabled", False)
            configured = svc.get("configured", False)
            missing = svc.get("missing_env_vars", [])
            note = svc.get("note")

            if configured and enabled:
                icon = "✅"
            elif enabled:
                icon = "⚠️"
            else:
                icon = "❌"

            line = f"{icon} **{name}** ({svc_type})"
            if note:
                line += f" — {note}"
            elif missing:
                line += f" — 缺少: {', '.join(missing)}"
            st.markdown(line)

st.divider()

# === 配置说明 ===

st.subheader("📝 配置说明")
st.markdown("""
- 配置保存到 `config/runtime_settings.json`（优先级高于 `.env`）
- API Key 不会在页面明文显示
- `runtime_settings.json` 已加入 `.gitignore`，不会提交到代码仓库
- 也可以直接编辑 `.env` 文件配置
""")
