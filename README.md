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

## 研究流程

```
用户输入主题
    │
    ▼
┌─ Planning ─────────────────────────────────────────────┐
│  主题理解 → 语言规划 → Query 扩展（中英双语）           │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Search ───────────────────────────────────────────────┐
│  Tavily / Brave / Google Books 并发搜索                 │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Processing ───────────────────────────────────────────┐
│  URL 去重 → 来源评分 → 分类（必读/图书/八卦/...）       │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Storage ──────────────────────────────────────────────┐
│  保存到 SQLite 数据库                                   │
└────────────────────────────────────────────────────────┘
    │
    ▼ (手动触发)
┌─ Export ───────────────────────────────────────────────┐
│  导出研究索引到 Obsidian Vault                          │
└────────────────────────────────────────────────────────┘
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

### 最小配置（纯规则模式，不需要 LLM）

```bash
# .env
ENABLE_LLM=false
TAVILY_API_KEY=tvly-xxxxx
```

### 云端 LLM 配置（推荐，无需本地 GPU）

在 Settings 页面中配置，或编辑 `.env`：

```bash
ENABLE_CLOUD_LLM=true
CLOUD_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_DEFAULT_MODEL=deepseek-chat
```

配置后在 Settings 页面将"当前默认 LLM Provider"切换为 `deepseek`。

### Ollama 局域网配置（可选）

```bash
ENABLE_LLM=true
OLLAMA_BASE_URL=http://192.168.1.50:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
```

### 搜索 Provider

```bash
TAVILY_API_KEY=tvly-xxxxx            # 必填（免费 1000 次/月）
BRAVE_API_KEY=BSA-xxxxx              # 可选
# Google Books 默认 Public Mode，无需 API Key
```

### Obsidian Vault

```bash
OBSIDIAN_VAULT_PATH=/Users/you/Obsidian/ResearchVault
```

## UI 页面

### Research（新建研究）

输入主题 → 选择模式/深度 → 开始研究 → 查看结果摘要 → 导出到 Obsidian。

### Results（研究结果工作台）

- 统计卡片：总来源 / 高质量 / 图书 / 已提取 / 八卦
- 导出区域：一键导出研究索引到 Obsidian Vault
- 筛选排序：按等级/类型/状态/关键词筛选，按质量/相关性排序
- 分类浏览：必读资料 / 一手资料 / 深度报道 / 图书 / 采访 / 八卦
- 执行流程 Trace：查看完整研究执行轨迹和 LLM 使用情况
- 研究索引预览：Markdown 格式预览
- 事件日志：任务执行事件时间线

### Settings（配置管理）

- Ollama 配置：地址 → 测试 → 模型列表 → 保存
- 云端 LLM：Provider → API Key → 测试 → 保存
- 搜索 Provider：Tavily / Brave / Google Books 配置
- Obsidian Vault：路径 → 测试 → 保存
- 全部服务状态详情：实时显示所有服务配置来源和状态

## Research Trace（执行轨迹）

每个研究任务都有完整的执行轨迹，方便排错和观察：

### 记录内容

- 语言规划结果（user_language → working_language → output_language）
- Query 扩展详情（英文/中文 query 数量）
- 搜索 Provider 调用（每个 provider 返回数量、耗时、错误）
- 去重统计（原始 → 去重后）
- 评分结果（S/A/B/C/D 分布）
- LLM 调用详情（provider、model、input/output chars、耗时）
- 任务总耗时

### LLM 可观测性

Trace 系统记录每个 LLM 任务的状态：

| 状态 | 含义 |
|------|------|
| ✅ used_llm | 实际调用了 LLM |
| 🔁 fallback | LLM 失败，使用规则版 |
| 🚫 skipped_disabled | 配置禁用 |
| ⏭️ skipped_not_reached | 流程未到达 |
| 🧩 skipped_not_implemented | 计划中，未实现 |
| ⚙️ rule_only | 确定性操作，不需要 LLM |

### API

```
GET /research/tasks/{id}/trace          # 完整事件列表（支持 level/phase 过滤）
GET /research/tasks/{id}/trace/summary  # 统计摘要
GET /research/tasks/{id}/trace/llm      # LLM 使用详情
```

## Research Language Planning（研究语言规划）

用户经常用中文输入研究主题，但高质量资料来自英文世界。语言规划层自动桥接这个鸿沟。

```
中文输入 → 主题理解 → canonical English entity → 英文 query 为主
                                                → 中文 query 为辅
                                                → 英文正文提取
                                                → 中文摘要/故事点/卡片
                                                → Obsidian 保存（中文摘要 + 英文原文）
```

| 用户输入 | canonical entity | working_language | search_strategy |
|---------|-----------------|-----------------|-----------------|
| 库克的童年故事 | Tim Cook | en | english_first |
| 黄仁勋早期创业 | Jensen Huang | en | english_first |
| OpenAI 宫斗 | OpenAI | en | english_first |
| 小米早期创业故事 | 小米 | zh | chinese_first |

## AI Gateway

AI Gateway 是 LLM 调用的统一入口，业务模块不直接调用 LLM Provider。

```
业务 Service → AIGateway.run_json(task_name, payload, schema)
                    │
                    ├── 加载 task config (config/llm_tasks.yaml)
                    ├── 渲染 prompt (config/prompt_templates/)
                    ├── LLMRouter → provider.generate()
                    ├── parse_as() → Pydantic model
                    ├── Trace 记录（provider/model/chars/duration）
                    └── 失败时 → LLMFallbackRequired → 规则版 fallback
```

### LLM 任务注册表

所有可能使用 LLM 的任务都在 `config/llm_tasks.yaml` 中注册：

| 任务 | 阶段 | 状态 | Prompt |
|------|------|------|--------|
| topic_understanding | planning | ✅ 已实现 | topic_understanding.zh.md |
| language_planning | planning | ✅ 已实现 | topic_understanding.zh.md |
| query_expansion | planning | ✅ 已实现 | query_expansion.zh.md |
| entity_extraction | analysis | ✅ 已实现 | entity_extraction.zh.md |
| document_summary | analysis | ✅ 已实现 | document_summary.zh.md |
| source_review | scoring | 🚫 禁用 | source_review.zh.md |
| gossip_classification | analysis | 🧩 计划中 | — |
| research_card_generation | synthesis | 🧩 计划中 | — |
| contradiction_detection | synthesis | 🧩 计划中 | — |
| timeline_extraction | analysis | 🧩 计划中 | — |
| reranking | processing | 🧩 计划中 | — |

### Fallback 机制

- 所有业务 service 均实现了规则版 fallback
- LLM 不可用不影响核心研究流程
- 纯规则模式（`ENABLE_LLM=false`）也能完成搜索 → 去重 → 评分 → 导出

## API 端点

### 研究任务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/research/tasks` | 创建研究任务 |
| GET | `/research/tasks/{id}` | 获取任务状态 |
| POST | `/research/tasks/{id}/run` | 执行研究 |
| GET | `/research/tasks/{id}/sources` | 获取来源列表（含完整字段） |
| GET | `/research/tasks/{id}/events` | 获取事件日志 |
| GET | `/research/tasks/{id}/trace` | 获取执行轨迹 |
| GET | `/research/tasks/{id}/trace/summary` | 轨迹摘要 |
| GET | `/research/tasks/{id}/trace/llm` | LLM 使用详情 |
| POST | `/research/tasks/{id}/export-index` | 导出研究索引到 Obsidian |

### 设置与配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/settings/health` | 系统健康状态 |
| GET | `/settings/services` | 所有服务配置状态 |
| GET | `/settings/llm` | LLM 配置状态 |
| POST | `/settings/llm/test` | 测试 LLM 连接 |
| GET | `/settings/llm/ollama` | Ollama 详细配置 |
| POST | `/settings/llm/ollama/save` | 保存 Ollama 配置 |
| GET | `/settings/llm/cloud` | 云端 LLM 配置 |
| POST | `/settings/llm/cloud/save` | 保存云端 LLM 配置 |
| POST | `/settings/llm/active-provider` | 切换默认 LLM Provider |
| GET | `/settings/search` | 搜索 Provider 状态 |
| POST | `/settings/search/save` | 保存搜索配置 |
| GET | `/settings/obsidian` | Obsidian Vault 状态 |
| POST | `/settings/obsidian/save` | 保存 Vault 路径 |

## 目录结构

```
research_collector/
├── app/
│   ├── main.py                          # FastAPI 应用入口
│   ├── ai/                              # AI Gateway 模块
│   │   ├── gateway.py                   # 统一 LLM 调用网关（含 Trace）
│   │   ├── router.py                    # Provider 路由
│   │   ├── tasks.py                     # 任务配置加载
│   │   ├── prompts.py                   # Prompt 模板管理
│   │   ├── parser.py                    # JSON 解析器
│   │   ├── schemas.py                   # LLM 输出 Schema
│   │   ├── budget.py                    # Token 预算
│   │   └── errors.py                    # AI 模块异常
│   ├── tracing/                         # Research Trace 系统
│   │   ├── __init__.py
│   │   ├── models.py                    # TraceEvent / TraceStep / TracePhase
│   │   ├── recorder.py                  # TraceRecorder / trace_span
│   │   └── llm_registry.py             # LLM Task Registry
│   ├── vault/                           # Vault Workspace 子系统
│   ├── api/
│   │   └── routes_settings.py           # 设置 API
│   ├── core/
│   │   ├── service_registry.py          # 服务配置中心
│   │   └── feature_flags.py             # 功能开关
│   ├── providers/llm/                   # LLM Provider 实现
│   └── services/                        # LLM 增强业务服务
├── api/                                 # HTTP 路由
│   ├── routes_research.py               # 研究任务 + Trace API
│   ├── routes_export.py                 # 导出 API
│   └── routes_sources.py               # 来源管理
├── core/
│   └── config.py                        # 集中配置（runtime_settings 覆盖）
├── models/                              # Pydantic 数据模型
├── db/                                  # SQLAlchemy 持久化
├── services/                            # 核心业务逻辑编排
├── providers/search/                    # 搜索 Provider（Tavily/Brave/Google Books）
├── config/
│   ├── llm_tasks.yaml                   # LLM 任务注册表
│   ├── providers.yaml                   # 服务注册表
│   ├── runtime_settings.json            # 运行时配置（.gitignore）
│   └── prompt_templates/                # Prompt 模板
├── templates/                           # Jinja2 Markdown 模板
├── ui/
│   ├── api_client.py                    # UI → API 客户端
│   └── pages/
│       ├── 1_Research.py                # 新建研究 + 导出
│       ├── 2_Results.py                 # 结果工作台 + Trace
│       └── 3_Settings.py               # 配置管理
├── tests/                               # 970+ 测试
├── start.sh                             # 一键启动脚本
├── pyproject.toml
├── Makefile
└── .env.example
```

## 测试

```bash
# 全量测试
python -m pytest

# 按模块测试
python -m pytest tests/test_research_service.py -v      # 研究流水线
python -m pytest tests/test_ai_gateway.py -v            # AI Gateway
python -m pytest tests/test_research_trace.py -v        # Trace 系统
python -m pytest tests/test_llm_observability.py -v     # LLM 可观测性
python -m pytest tests/test_llm_task_registry.py -v     # LLM 任务注册表
python -m pytest tests/test_settings_routes.py -v       # Settings API
python -m pytest tests/test_export_routes.py -v         # 导出 API
python -m pytest tests/test_service_registry.py -v      # 服务状态
python -m pytest tests/test_settings_persistence.py -v  # 配置持久化
python -m pytest tests/test_markdown_export_index.py -v # Markdown 导出

# 覆盖率
python -m pytest --cov=app --cov=services --cov=providers
```

## 设计原则

- **低耦合**：每个模块职责单一，通过接口通信
- **可降级**：LLM 不可用时规则 fallback 覆盖核心流程
- **可观测**：Research Trace 记录完整执行轨迹，LLM 调用透明
- **安全**：API Key 不明文显示，Trace 自动脱敏
- **原子写入**：配置文件使用 tmp + rename 避免损坏
- **不覆盖原文**：Obsidian 笔记保留英文原文，中文摘要在前

## 未来扩展

- YouTube Transcript Provider
- Internet Archive Provider
- 向量存储 (LanceDB)
- 知识图谱 (NetworkX)
- 矛盾检测服务
- 多轮深度研究
- Vault 增量同步
- Backlinks 自动维护
- 日文/韩文输入支持
- LLM Reranking（可选）
- Research Card 自动生成
