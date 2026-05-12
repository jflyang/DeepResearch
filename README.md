# Research Collector - 慢速深度研究资料收集器

本地研究工作台：输入研究主题 → 自动扩展搜索词 → 多源搜索 → 去重评分分类 → 下载提取正文 → LLM 分析 → 沉淀至 Obsidian Vault。

## 架构

```
┌────────────────┐      ┌────────────────┐      ┌────────────────────────────┐
│  Streamlit UI  │─────▶│  FastAPI API   │─────▶│  Services (业务编排)        │
└────────────────┘      └────────────────┘      └────────────────────────────┘
                                                         │
                         ┌───────────────────────────────┼───────────────────┐
                         ▼                   ▼           ▼                   ▼
              ┌─────────────────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────┐
              │    AI Gateway       │ │  Scoring   │ │ Extract  │ │ Vault Manager│
              │  ┌───────────────┐  │ │  Service   │ │ Provider │ │  (写入唯一   │
              │  │ LLM Router    │  │ └────────────┘ └──────────┘ │   入口)      │
              │  └───┬───────┬───┘  │                             └──────────────┘
              │      │       │      │                                     │
              │      ▼       ▼      │                                     ▼
              │  ┌──────┐ ┌──────┐  │                             ┌──────────────┐
              │  │Ollama│ │Cloud │  │                             │ Obsidian     │
              │  │ LAN  │ │ API  │  │                             │ Vault        │
              │  └──────┘ └──────┘  │                             └──────────────┘
              └─────────────────────┘
```

## Research Language Planning（研究语言规划）

用户经常用中文输入研究主题，但高质量资料来自英文世界。语言规划层自动桥接这个鸿沟。

### 流程

```
中文输入 → 主题理解 → canonical English entity → 英文 query 为主
                                                → 中文 query 为辅
                                                → 英文正文提取
                                                → 中文摘要/故事点/卡片
                                                → Obsidian 保存（中文摘要 + 英文原文）
```

### 示例

| 用户输入 | canonical entity | working_language | search_strategy |
|---------|-----------------|-----------------|-----------------|
| 库克的童年故事 | Tim Cook | en | english_first |
| 黄仁勋早期创业 | Jensen Huang | en | english_first |
| OpenAI 宫斗 | OpenAI | en | english_first |
| 小米早期创业故事 | 小米 | zh | chinese_first |
| Tesla 收购 SolarCity 争议 | Tesla | en | english_first |

### 架构组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `LanguageCode` enum | `models/enums.py` | zh / en / mixed / unknown |
| `SearchStrategy` enum | `models/enums.py` | english_first / chinese_first / bilingual |
| `ResearchLanguagePlan` | `models/schemas.py` | 语言策略数据模型 |
| `ExpandedQuery` | `models/schemas.py` | 带语言追溯的查询模型 |
| `ResearchLanguagePlannerService` | `app/services/research_language_planner.py` | 语言规划服务（LLM + 规则 fallback） |
| `QueryExpansionService` | `services/query_expansion_service.py` | 语言感知的查询扩展 |
| `ResearchService` | `services/research_service.py` | 集成语言规划的研究流水线 |

### 设计原则

- **低耦合**：语言规划独立成 service，search provider 只接收 query，不负责翻译
- **可降级**：LLM 不可用时规则 fallback 覆盖常见中文实体映射
- **可排错**：每个 ExpandedQuery 记录 language / canonical_entity / original_user_term
- **不覆盖原文**：Markdown 输出保留英文原文，中文摘要在前

### Markdown 双语输出

当 `source_language=en` 且 `output_language=zh` 时，生成的 Obsidian 笔记结构：

```markdown
---
source_language: en
output_language: zh
canonical_topic: "Tim Cook childhood story"
original_topic: "库克的童年故事"
query_language: en
matched_query: "Tim Cook childhood Robertsdale Alabama"
---

# 中文摘要
（中文分析内容）

# 为什么值得看
（中文）

# 关键事实
- ...

# 原文信息
- 原文标题：Tim Cook's Early Life
- 原文语言：en
- 匹配 query：Tim Cook childhood Robertsdale Alabama

# 原文正文
（完整英文原文，不翻译）
```

## 快速开始

```bash
# 一键启动（推荐）
./start.sh

# 或分步启动
make install           # 安装依赖
cp .env.example .env   # 配置
make api               # 启动后端 (http://localhost:8000)
make ui                # 启动前端 (http://localhost:8501)
```

`start.sh` 会同时启动后端和前端，Ctrl+C 一键停止所有服务。

## 配置

### 配置优先级

```
config/runtime_settings.json > .env > 默认值
```

- **runtime_settings.json**：通过 Settings 页面保存的配置（API Key、Ollama 地址、Vault 路径等）
- **.env**：环境变量文件
- **默认值**：代码中的 fallback

`runtime_settings.json` 已加入 `.gitignore`，不会提交到代码仓库。

### 最小配置（纯规则模式）

```bash
# .env
ENABLE_LLM=false
TAVILY_API_KEY=tvly-xxxxx
```

### Ollama 局域网配置

```bash
ENABLE_LLM=true
OLLAMA_BASE_URL=http://192.168.1.50:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
OLLAMA_TIMEOUT_SECONDS=120
```

也可以在 Settings 页面中直接配置，无需编辑 `.env`。

### 云端 LLM 配置（DeepSeek / OpenAI / OpenAI-Compatible）

```bash
ENABLE_CLOUD_LLM=true
CLOUD_LLM_PROVIDER=deepseek          # deepseek / openai / openai_compatible
CLOUD_LLM_TIMEOUT_SECONDS=120

# DeepSeek
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_DEFAULT_MODEL=deepseek-v4-flash

# OpenAI
OPENAI_API_KEY=sk-xxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_DEFAULT_MODEL=gpt-4.1-mini

# OpenAI-Compatible（任意兼容 API）
OPENAI_COMPATIBLE_API_KEY=sk-xxxxx
OPENAI_COMPATIBLE_BASE_URL=https://your-api.com/v1
OPENAI_COMPATIBLE_DEFAULT_MODEL=your-model
```

### 搜索 Provider

```bash
TAVILY_API_KEY=tvly-xxxxx            # 必填（免费 1000 次/月）
BRAVE_API_KEY=BSA-xxxxx              # 可选
GOOGLE_BOOKS_API_KEY=AIza-xxxxx      # 可选，不填则 Public Mode
```

### Obsidian Vault

```bash
OBSIDIAN_VAULT_PATH=/Users/you/Obsidian/ResearchVault
```

### 测试 Ollama 连接

```bash
python scripts/test_ollama_connection.py
```

## Settings 页面

Settings 页面（`http://localhost:8501` → 左侧 Settings）提供完整的可视化配置能力：

| 区域 | 功能 |
|------|------|
| 🦙 局域网 Ollama 配置 | 输入地址 → 测试连接 → 刷新模型列表 → 选择模型 → 保存 |
| ☁️ 云端大模型 API | 选择 Provider → 填写 API Key → 测试连接 → 获取模型 → 保存 |
| 🎯 当前默认 LLM Provider | 一键切换 Ollama / DeepSeek / OpenAI |
| 🔌 搜索 Provider 配置 | 启用/禁用 + 填写 API Key + 保存 |
| 📁 Obsidian Vault | 输入路径 → 测试路径 → 保存 |

所有配置保存到本地 `config/runtime_settings.json`，API Key 不会明文显示在页面上。

## AI Gateway 架构

AI Gateway 是 LLM 调用的统一入口，业务模块不直接调用 LLM Provider。

```
业务 Service → AIGateway.run_json(task_name, payload, schema)
                    │
                    ├── 加载 task config (config/llm_tasks.yaml)
                    ├── 渲染 prompt (config/prompt_templates/)
                    ├── 应用 max_input_chars 截断
                    ├── LLMRouter.get_provider(provider_name)
                    ├── provider.generate(LLMRequest) → LLMResponse
                    ├── parse_as(response.text, schema) → Pydantic model
                    └── 失败时 → LLMFallbackRequired / LLMTaskFailed
```

### 支持的 LLM Provider

| Provider | 类型 | 用途 |
|----------|------|------|
| `ollama_lan` | Ollama | 本地/局域网模型 |
| `deepseek` | OpenAI-compatible | DeepSeek 云端 API |
| `openai` | OpenAI-compatible | OpenAI 官方 API |
| `openai_compatible` | OpenAI-compatible | 任意兼容 API |
| `mock_llm` | Mock | 测试用 |

### Active Provider 机制

`config/llm_tasks.yaml` 中任务可设置 `provider: active`，运行时自动解析为当前活跃 Provider（通过 Settings 页面切换）。

### LLM 任务

每个任务可独立配置 provider、model、temperature 等参数：

| 任务 | 用途 | 默认 Provider |
|------|------|---------------|
| `topic_understanding` | 主题分析 + 语言规划 | ollama_lan |
| `query_expansion` | 查询扩展（语言感知） | active（当前默认） |
| `entity_extraction` | 实体提取 | ollama_lan |
| `source_review` | 来源评审 | ollama_lan |
| `document_summary` | 文档摘要（双语） | ollama_lan |
| `research_card_generation` | 卡片生成 | ollama_lan |
| `contradiction_detection` | 矛盾检测 | ollama_lan |
| `language_planning` | 研究语言规划 | ollama_lan |

### Prompt Templates

每个 LLM 任务对应一个专业 Prompt Template（`config/prompt_templates/`），采用"研究 Agent"设计：

| 模板 | 角色定位 | 核心要求 |
|------|----------|----------|
| `topic_understanding.zh.md` | 资深研究助理 | 判断主题类型、识别 canonical entity、决定语言策略 |
| `query_expansion.zh.md` | 调查记者研究助理 | 按语言策略生成中英比例合适的搜索词 |
| `entity_extraction.zh.md` | 档案研究员 | 抽取值得建档的实体，判断研究价值 |
| `source_review.zh.md` | 事实核查编辑 | 识别 SEO 洗稿/转载/AI 农场，判断信息密度 |
| `document_summary.zh.md` | 播客研究助理 | 英文原文中文摘要、保留关键英文名词、提取故事点 |

所有 Prompt 强制 JSON-only 输出，禁止 markdown/code block/解释文字。

### Fallback 机制

- `require_llm: false`（默认）：LLM 失败时抛出 `LLMFallbackRequired`，业务层使用规则版
- `require_llm: true`：LLM 失败时抛出 `LLMTaskFailed`，任务中断
- 所有业务 service 均实现了规则版 fallback，LLM 不可用不影响核心流程

## Vault Workspace 架构

Vault 是长期研究 Workspace，不是简单的一次性导出。VaultManager 是唯一允许写 Vault 文件的组件。

```
VaultManager
    │
    ├── ensure_workspace()          # 创建基础目录
    ├── ensure_topic_workspace()    # 创建 topic 子目录
    ├── save_source_note()          # 保存来源笔记
    ├── save_topic_index()          # 保存研究索引
    ├── save_entity_note()          # 创建 entity note（幂等）
    ├── save_concept_note()         # 创建 concept note（幂等）
    ├── save_card()                 # 保存研究卡片
    └── ensure_attachment_dir()     # 确保附件目录
```

### Vault 目录结构

```
Vault Root/
├── Topics/
│   └── {topic}/
│       ├── index.md                # 研究索引（含 wikilinks）
│       ├── sources/                # 来源笔记
│       │   └── 2026-05-11_title-slug_domain.md
│       ├── cards/                  # 研究卡片
│       ├── timeline/               # 时间线
│       └── attachments/            # 附件
├── Entities/
│   └── {entity_name}.md           # 人物/组织 note
└── Concepts/
    └── {concept_name}.md          # 概念 note
```

### 设计原则

- **唯一写入入口**：业务 service 不允许直接 `open(path, "w")`
- **路径集中管理**：`vault/paths.py` + `vault/naming.py`
- **不覆盖原则**：`overwrite=False` 时自动加后缀，entity note 幂等
- **Wikilinks**：已知 entity 自动替换为 `[[entity]]`
- **Frontmatter**：YAML 合法序列化，ISO8601 时间
- **低耦合**：VaultManager 不调用搜索、LLM、数据库、UI

## API 端点

### 研究任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/research/tasks` | 创建研究任务 |
| GET | `/research/tasks/{id}` | 获取任务状态 |
| POST | `/research/tasks/{id}/run` | 执行研究 |
| GET | `/research/tasks/{id}/sources` | 获取来源列表 |
| GET | `/research/tasks/{id}/events` | 获取事件日志 |
| POST | `/research/tasks/{id}/export-index` | 导出 Obsidian |

### 设置与配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/settings/health` | 系统健康状态 |
| GET | `/settings/services` | 所有服务配置状态 |
| GET | `/settings/llm` | LLM 配置状态 |
| POST | `/settings/llm/test` | 测试 LLM 连接 |
| GET | `/settings/llm/ollama` | Ollama 详细配置 |
| POST | `/settings/llm/ollama/test` | 测试 Ollama 连接 |
| POST | `/settings/llm/ollama/models` | 获取 Ollama 模型列表 |
| POST | `/settings/llm/ollama/save` | 保存 Ollama 配置 |
| GET | `/settings/llm/cloud` | 云端 LLM 配置 |
| POST | `/settings/llm/cloud/test` | 测试云端 LLM 连接 |
| POST | `/settings/llm/cloud/models` | 获取云端模型列表 |
| POST | `/settings/llm/cloud/save` | 保存云端 LLM 配置 |
| POST | `/settings/llm/active-provider` | 切换默认 LLM Provider |
| GET | `/settings/search` | 搜索 Provider 状态 |
| POST | `/settings/search/save` | 保存搜索配置 |
| GET | `/settings/obsidian` | Obsidian Vault 状态 |
| POST | `/settings/obsidian/test` | 测试 Vault 路径 |
| POST | `/settings/obsidian/save` | 保存 Vault 路径 |

## 目录结构

```
research_collector/
├── app/
│   ├── main.py                          # FastAPI 应用入口
│   ├── ai/                              # AI Gateway 模块
│   │   ├── gateway.py                   # 统一 LLM 调用网关
│   │   ├── router.py                    # Provider 路由（支持 runtime 覆盖）
│   │   ├── tasks.py                     # 任务配置加载（支持 active provider）
│   │   ├── prompts.py                   # Prompt 模板管理（Jinja2）
│   │   ├── parser.py                    # JSON 解析器
│   │   ├── schemas.py                   # LLM 输出 Schema
│   │   ├── budget.py                    # Token 预算与输入截断
│   │   └── errors.py                    # AI 模块异常
│   ├── vault/                           # Vault Workspace 子系统
│   ├── api/
│   │   └── routes_settings.py           # 设置 API（Ollama/Cloud/Search/Obsidian）
│   ├── core/
│   │   ├── service_registry.py          # 服务配置中心
│   │   └── feature_flags.py            # 功能开关
│   ├── providers/
│   │   └── llm/
│   │       ├── base.py                  # LLM Provider 抽象基类
│   │       ├── ollama.py                # Ollama（含 list_models）
│   │       ├── openai_compatible.py     # DeepSeek/OpenAI/Compatible（含 list_models）
│   │       └── mock.py                  # 测试用 Mock
│   └── services/                        # LLM 增强业务服务
│       └── research_language_planner.py # 研究语言规划服务
├── api/                                 # HTTP 路由
├── core/
│   └── config.py                        # 集中配置（支持 runtime_settings.json 覆盖）
├── models/                              # Pydantic 数据模型
│   ├── enums.py                         # 枚举（含 LanguageCode, SearchStrategy）
│   └── schemas.py                       # 业务模型（含 ResearchLanguagePlan, ExpandedQuery）
├── db/                                  # 持久化
├── services/                            # 核心业务逻辑编排
│   ├── research_service.py              # 研究流水线（集成语言规划）
│   ├── query_expansion_service.py       # 查询扩展（语言感知）
│   └── markdown_service.py             # Markdown 导出（双语结构）
├── providers/                           # 外部 API 封装（搜索/提取）
├── config/
│   ├── llm_tasks.yaml                   # LLM 任务配置
│   ├── providers.yaml                   # Provider 注册表
│   ├── runtime_settings.json            # 运行时配置（.gitignore）
│   └── prompt_templates/                # 专业研究 Agent Prompt
├── templates/
│   ├── source_note.md.j2               # 来源笔记模板（支持双语）
│   └── research_index.md.j2            # 研究索引模板
├── ui/
│   ├── streamlit_app.py
│   ├── api_client.py                    # UI → API 客户端
│   └── pages/
│       ├── 1_Research.py
│       ├── 2_Results.py
│       └── 3_Settings.py               # 可视化配置页面
├── tests/                               # 842+ 测试
├── start.sh                             # 一键启动脚本
├── pyproject.toml
├── Makefile
└── .env.example
```

## 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `core/` | 配置、日志、错误定义 | 无 |
| `models/` | 数据契约（Pydantic） | `core/` |
| `db/` | 持久化 | `core/`, `models/` |
| `providers/` | 外部 API 封装 | `core/`, `models/` |
| `app/ai/` | LLM Gateway | `app/providers/llm/`, `config/` |
| `app/vault/` | Vault Workspace 管理 | `config/vault.yaml` |
| `app/services/` | LLM 增强业务服务（含语言规划） | `app/ai/`, `services/` |
| `services/` | 核心业务逻辑编排 | `providers/`, `db/`, `models/` |
| `api/` | HTTP 路由 | `services/`, `models/` |
| `ui/` | 用户界面 | 通过 HTTP 调用 `api/` |
| `config/` | YAML/JSON 配置文件 | 被各模块读取 |

## 测试

```bash
# 全量测试（842+ tests）
python -m pytest

# AI Gateway
python -m pytest tests/test_ai_gateway.py tests/test_ai_parser.py tests/test_ai_schemas.py -v

# 语言规划
python -m pytest tests/test_language_schemas.py tests/test_research_language_planner.py -v

# 语言规划端到端
python -m pytest tests/test_language_planning_flow.py -v

# Query Expansion（语言感知）
python -m pytest tests/test_query_expansion.py tests/test_query_expansion_language.py -v

# Markdown 双语输出
python -m pytest tests/test_markdown.py tests/test_markdown_language_output.py -v

# LLM Providers
python -m pytest tests/test_ollama_provider.py tests/test_openai_compatible_provider.py -v

# Cloud Provider 路由
python -m pytest tests/test_llm_router_cloud_provider.py -v

# Settings API
python -m pytest tests/test_settings_routes.py -v

# Vault
python -m pytest tests/test_vault_paths.py tests/test_vault_naming.py tests/test_vault_manager.py tests/test_wikilinks.py -v

# Prompt Templates
python -m pytest tests/test_prompt_store.py tests/test_topic_understanding_prompt.py -v

# 集成测试
python -m pytest tests/test_llm_gateway_integration.py -v

# 覆盖率
python -m pytest --cov=app --cov=services --cov=providers
```

## 未来扩展

- `providers/search/youtube.py` — YouTube Transcript
- `providers/search/internet_archive.py` — Internet Archive
- 向量存储 (LanceDB)
- 知识图谱 (NetworkX)
- 矛盾检测服务
- 多轮深度研究
- Vault 增量同步
- Backlinks 自动维护
- 语言规划 LLM prompt 优化（更多实体覆盖）
- 日文/韩文输入支持
