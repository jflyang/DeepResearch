# DeepResearch — 深度研究资料收集与合成工作台

本地优先的研究工作台。输入一个主题，自动完成搜索、抓取、归一化、去重、合成，最终输出一篇有来源引用的结构化研究文档到 Obsidian Vault。

支持三条研究路径：

1. **自动研究**：输入主题 → 搜索扩展 → 多源搜索 → 评分分类 → 自动抓取 S/A/B 级来源正文 → 英文内容自动翻译为中英对照 → 内容归一化 → 跨来源去重 → LLM 合成研究文档 → 写入 Obsidian。
2. **外部报告导入**：粘贴 GPT / Perplexity / Claude 生成的研究报告 → 解析引用 → 抓取正文 → 补充检索书籍/论文 → 合成导出。
3. **手动合成**：在 Results 页面对已有来源手动触发"清洗并合成研究文档"，生成 `research.md`。

## 核心特性

- **多源搜索**：SearXNG、Open Library、Crossref、arXiv、Wikipedia、Tavily、Brave、Google Books
- **智能评分**：来源按 S/A/B/C/D 五级评估，自动过滤噪音
- **异步网页抓取**：点击提取后加入后台队列，不阻塞 UI，支持连续提取多个来源
- **Crawlee 深度抓取**：支持 HTTP / Browser / Adaptive 模式，相关性过滤后批量抓取
- **英文自动翻译**：提取的英文内容自动调用 LLM 翻译为中英对照格式，直接保存到 sources 目录
- **内容归一化**：LLM 将非结构化正文拆解为可追溯的结构化事实条目
- **跨来源去重**：相同事实合并，来源冲突标记，多源确认提升可信度
- **研究合成**：LLM 将去重后的事实组织为有叙事性的研究文档（`research.md`）
- **Obsidian 输出**：生成结构化研究文档（概览、核心摘要、已确认事实、时间线、人物、地点、概念、故事点、图书、冲突、来源地图、下一步）
- **全程可降级**：LLM 不可用时规则 fallback 覆盖所有环节
- **执行轨迹**：Research Trace 记录每一步的 provider、耗时、输入输出，产品化展示
- **统一设计系统**：所有页面使用统一 CSS、组件库、状态展示

## 架构

```
┌────────────────┐      ┌────────────────┐      ┌──────────────────────────────┐
│  Streamlit UI  │─────▶│  FastAPI API   │─────▶│  Services（业务编排）          │
└────────────────┘      └────────────────┘      └──────────────────────────────┘
                                                          │
                    ┌─────────────────────────────────────┼──────────────────────┐
                    ▼                    ▼                 ▼                      ▼
         ┌───────────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐
         │    AI Gateway     │  │  Crawlers   │  │  Scoring /   │  │  Markdown Export  │
         │  ┌─────────────┐  │  │  (Crawlee)  │  │  Dedup /     │  │  → Obsidian Vault │
         │  │ LLM Router  │  │  └─────────────┘  │  Classify    │  └──────────────────┘
         │  └──┬──────┬───┘  │                    └──────────────┘
         │     │      │      │
         │     ▼      ▼      │
         │ ┌──────┐┌──────┐  │
         │ │Ollama││Cloud │  │
         │ │ LAN  ││ API  │  │
         │ └──────┘└──────┘  │
         └───────────────────┘
```

## 研究流程

```
用户输入主题
    │
    ▼
┌─ Planning ─────────────────────────────────────────────────────┐
│  主题理解 → 语言规划 → Query 扩展（中英双语）                    │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Search ───────────────────────────────────────────────────────┐
│  SearXNG / Wikipedia / Open Library / Crossref / arXiv 并发搜索 │
│  （可选：Tavily / Brave / Google Books）                         │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Processing ───────────────────────────────────────────────────┐
│  URL 去重 → 来源评分（S/A/B/C/D）→ 分类                         │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Extraction（异步队列）────────────────────────────────────────┐
│  后台队列逐个抓取 → Trafilatura 提取正文                         │
│  英文内容 → LLM 翻译为中英对照 → 直接保存 .md 到 sources/       │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Content Normalization ────────────────────────────────────────┐
│  每篇正文 → LLM 拆解为结构化事实条目（含 evidence_text 溯源）    │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Cross-Source Deduplication ───────────────────────────────────┐
│  相同事实合并 → 来源冲突标记 → 多源确认提升可信度                 │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Research Synthesis ───────────────────────────────────────────┐
│  LLM 合成研究文档 → 分类为已确认/待核验/冲突/故事点              │
└────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─ Export ───────────────────────────────────────────────────────┐
│  渲染 Markdown → 写入 Obsidian Vault research.md                │
└────────────────────────────────────────────────────────────────┘
```

## 快速开始

```bash
# 一键启动
./start.sh

# 或分步启动
cp .env.example .env   # 配置环境变量
make install           # 安装依赖
make api               # 启动后端 http://localhost:8000
make ui                # 启动前端 http://localhost:8501
```

### 系统要求

- Python 3.11+
- 可选：Ollama（本地 LLM）或 DeepSeek/OpenAI API Key（云端 LLM）
- 可选：SearXNG 实例（免费搜索）
- 可选：Playwright（浏览器抓取模式）

## 配置

配置优先级：`config/runtime_settings.json` > `.env` > 默认值

### 最小配置（免费模式，无需 API Key）

```bash
ENABLE_LLM=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=qwen3:8b
ENABLE_SEARXNG=true
SEARXNG_BASE_URL=http://localhost:8080
OBSIDIAN_VAULT_PATH=/path/to/your/vault
```

### 云端 LLM（推荐，无需本地 GPU）

```bash
ENABLE_CLOUD_LLM=true
CLOUD_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_DEFAULT_MODEL=deepseek-chat
```

### 搜索 Provider

| Provider | 类型 | 需要 Key | 说明 |
|----------|------|----------|------|
| SearXNG | 通用网页 | 否（自托管） | 推荐，免费无限制 |
| Wikipedia | 实体消歧 | 否 | 人物/事件背景 |
| Open Library | 图书 | 否 | 图书元数据 |
| Crossref | 论文 | 否 | 学术论文 DOI |
| arXiv | 论文 | 否 | 预印本 |
| Tavily | 通用网页 | 是 | 高质量搜索 |
| Brave | 通用网页 | 是 | 备选搜索 |
| Google Books | 图书 | 可选 | 图书详情 |

## UI 页面

| # | 页面 | 功能 |
|---|------|------|
| 1 | Research | 创建研究任务（Simple / Advanced / Batch），实时查看执行流程 |
| 2 | Results | 研究结果工作台：来源筛选、异步提取、合成研究文档、Trace、导出 |
| 3 | Report Ingestion | 导入外部 AI 研究报告，解析引用，补充检索 |
| 4 | External Signals | 外部信号源（TrendRadar 等，开发中） |
| 9 | Settings | LLM / 搜索 Provider / Obsidian Vault / 服务优先级配置 |

### UI 设计系统

项目使用统一的 UI 组件库（`ui/components/`），包括：

- **layout.py**：页面头部、Section、分隔线、空状态/错误/成功/警告提示
- **status.py**：统一 Badge（任务状态、来源等级、下载状态、LLM 任务状态）
- **cards.py**：统计卡片、信息卡片
- **trace_panel.py**：产品化 Trace 面板（摘要 + 筛选 + Timeline）
- **source_cards.py**：来源卡片
- **forms.py**：表单 Section、配置项
- **task_queue_panel.py**：任务队列面板

全局样式通过 `ui/styles.py` 的 `apply_global_styles()` 注入。

## 异步提取与翻译

提取流程已升级为异步队列模式：

1. 点击"提取"按钮 → 立即加入后台队列，UI 不阻塞
2. 可连续点击多个来源的提取按钮，队列逐个处理
3. 提取完成后自动检测语言：英文内容调用 LLM 翻译为中英对照格式
4. 翻译后的 .md 文件直接保存到 `Obsidian/Research/{topic}/sources/`
5. 无需手动导出，提取即保存

### 提取队列 API

```
POST   /sources/{id}/extract-async       异步提取（加入队列）
POST   /sources/extract-batch-async      批量异步提取
GET    /sources/extraction-queue/status   队列状态
GET    /sources/{id}/extraction-status    单个来源提取状态
```

## 内容归一化与研究合成

这是系统的核心差异化能力。传统研究工具只收集来源列表，DeepResearch 进一步将来源正文合成为可用的研究文档。

### 流程

1. **ContentNormalizationService**：对每篇已抓取正文，LLM 提取结构化事实条目（claim + evidence_text + 实体 + 置信度）
2. **CrossSourceDeduplicationService**：跨来源合并相同事实，标记冲突，多源确认提升可信度
3. **ResearchSynthesisService**：编排归一化 → 去重 → LLM 合成，生成 SynthesizedResearchDocument
4. **FileBased SynthesisService**：从 `sources/` 目录读取已保存的 .md 文件，合并为 `research.md`

### 核心原则

- 只处理已抓取成功的正文，搜索摘要不能变成 confirmed fact
- 每条事实必须可追溯 source_id / document_id / url
- LLM 不得编造来源中没有的信息
- 来源冲突标记为"待核验"
- S/A/B 级来源参与合成，C/D 级排除
- B 级来源支持的事实标记 confidence=medium
- B 级事实被 S/A 来源交叉确认时可提升可信度
- LLM 失败时 fallback 到规则合成，不让流程中断

### 策略配置

`config/research_policy.yaml`：

```yaml
auto_fetch:
  include_levels: ["S", "A", "B"]
auto_normalization:
  include_levels: ["S", "A", "B"]
auto_synthesis:
  enabled: true
  include_levels: ["S", "A", "B"]
  min_extracted_documents: 1
  run_after_auto_fetch: true
```

## AI Gateway

统一 LLM 调用入口，业务模块不直接调用 Provider。

```
Service → AIGateway.run_json(task_name, payload, schema)
              │
              ├── 加载 config/llm_tasks.yaml
              ├── 渲染 config/prompt_templates/{task}.{lang}.md
              ├── LLMRouter → provider.generate()
              ├── parse_as() → Pydantic model
              ├── Trace 记录
              └── 失败 → LLMFallbackRequired → 规则版
```

### LLM 任务

| 任务 | 阶段 | 说明 |
|------|------|------|
| topic_understanding | planning | 主题理解 + 语言规划 |
| query_expansion | planning | 搜索词扩展 |
| query_translation | planning | 查询翻译 |
| content_translation | export | 英文内容翻译为中英对照 |
| document_summary | analysis | 正文摘要与实体提取 |
| entity_extraction | analysis | 实体提取 |
| content_normalization | synthesis | 正文归一化为结构化事实 |
| cross_source_deduplication | synthesis | 跨来源去重与冲突检测 |
| research_synthesis | synthesis | 研究文档合成 |
| report_understanding | ingestion | 外部报告理解 |
| report_reference_extraction | ingestion | 报告引用提取 |

## Research Trace

执行轨迹系统记录研究任务的每一步操作，产品化展示而非原始 JSON。

### Trace 格式化

`app/tracing/formatters.py` 提供：

- `format_trace_event_summary(event)` — 产品化可读摘要
- `get_trace_event_icon(event)` — 事件图标
- `get_trace_event_title(event)` — 中文标题
- `format_duration_ms(ms)` — 时间格式化（450ms / 2.30s / 1m 5s）
- `sanitize_trace_payload(payload)` — 自动脱敏（api_key、secret 等）

### 脱敏规则

- **保留**：max_output_tokens、input_tokens、output_tokens、token_count
- **脱敏**：api_key、authorization、access_token、refresh_token、secret、password、private_key、cookie

### Trace 展示示例

```
🤖 LLM 调用完成 — query_expansion / deepseek / 2.30s
🔎 搜索完成 — searxng / 18 条结果 / 1.50s
⚠️ 搜索失败 — Google Books rate limited
✅ 研究完成 — 总耗时 45.00s
```

## API 端点

### 研究任务

```
POST   /research/tasks                    创建任务
POST   /research/tasks/{id}/run           执行研究
GET    /research/tasks/{id}               任务状态
GET    /research/tasks/{id}/sources       来源列表
POST   /research/tasks/{id}/synthesize    执行合成（→ research.md）
POST   /research/tasks/{id}/export-index  导出研究索引
GET    /research/tasks/{id}/trace         执行轨迹
GET    /research/tasks/{id}/trace/summary 轨迹摘要
GET    /research/tasks/{id}/trace/llm     LLM 使用详情
```

### 任务管理

```
GET    /research/tasks                    任务列表（支持搜索/筛选/分页）
PATCH  /research/tasks/{id}              重命名
DELETE /research/tasks/{id}              删除（软删除）
POST   /research/tasks/{id}/clone        复制
POST   /research/tasks/{id}/rerun        重新运行
```

### 任务队列

```
GET    /research/tasks/queue              队列状态
POST   /research/tasks/enqueue            加入队列
POST   /research/tasks/batch-create       批量创建并入队
POST   /research/tasks/{id}/cancel        取消排队任务
POST   /research/tasks/{id}/retry         重试失败任务
POST   /research/tasks/worker/start       启动 Worker
POST   /research/tasks/worker/stop        停止 Worker
```

### 来源提取

```
POST   /sources/{id}/extract              同步提取
POST   /sources/{id}/extract-async        异步提取（推荐）
POST   /sources/extract-batch-async       批量异步提取
GET    /sources/extraction-queue/status   提取队列状态
GET    /sources/{id}/extraction-status    单个提取状态
GET    /sources/{id}/content              已提取内容
```

### 报告导入

```
POST   /research/import-report            创建导入任务
POST   /research/import-report/{id}/parse 解析引用
POST   /research/import-report/{id}/run   执行抓取
```

### 设置

```
GET    /settings/health                   健康检查
GET    /settings/services                 服务状态列表
GET    /settings/llm                      LLM 配置
GET    /settings/search                   搜索配置
GET    /settings/obsidian                 Obsidian 配置
POST   /settings/obsidian/save            保存 Vault 路径
GET    /settings/service-priority         服务优先级
POST   /settings/service-priority/save    保存优先级
```

## 目录结构

```
DeepResearch/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── ai/                        # AI Gateway
│   │   ├── gateway.py             # 统一 LLM 调用入口
│   │   ├── router.py              # Provider 路由
│   │   ├── tasks.py               # 任务配置加载
│   │   ├── prompts.py             # Prompt 模板渲染
│   │   ├── parser.py              # JSON 解析与校验
│   │   ├── schemas.py             # 输出 Schema
│   │   ├── budget.py              # 输入预算控制
│   │   └── errors.py              # LLM 异常定义
│   ├── tracing/                   # Research Trace
│   │   ├── recorder.py            # 事件记录器
│   │   ├── models.py              # TraceEvent / TraceStep / TracePhase
│   │   ├── formatters.py          # 产品化格式化 + 脱敏
│   │   └── llm_registry.py        # LLM 任务状态注册
│   ├── crawlers/                  # 网页抓取
│   │   ├── crawlee_service.py     # Crawlee 引擎
│   │   ├── relevance_filter.py    # 相关性过滤
│   │   ├── content_extractor.py   # HTML 正文提取
│   │   └── base.py                # 抓取基类
│   ├── services/                  # LLM 增强服务
│   │   ├── content_normalization_service.py
│   │   ├── cross_source_deduplication_service.py
│   │   ├── research_synthesis_service.py
│   │   ├── file_based_synthesis_service.py
│   │   ├── document_analysis_service.py
│   │   └── ...
│   ├── providers/llm/             # LLM Provider
│   │   ├── ollama.py              # Ollama 局域网
│   │   ├── openai_compatible.py   # OpenAI / DeepSeek / 兼容 API
│   │   ├── mock.py                # 测试用 Mock
│   │   └── base.py                # Provider 基类
│   └── core/                      # 服务注册 / Feature Flags
├── api/                           # HTTP 路由
│   ├── routes_research.py         # 研究任务 CRUD + 执行
│   ├── routes_sources.py          # 来源提取（含异步队列）
│   ├── routes_export.py           # 导出
│   └── routes_tasks.py            # 任务队列
├── services/                      # 核心业务编排
│   ├── research_service.py        # 研究主流程
│   ├── extraction_service.py      # 正文提取
│   ├── markdown_service.py        # Markdown 导出
│   └── ...
├── providers/search/              # 搜索 Provider
│   ├── tavily.py
│   ├── brave.py
│   ├── searxng.py
│   ├── open_library.py
│   ├── crossref.py
│   ├── arxiv.py
│   └── wikipedia.py
├── models/                        # Pydantic 数据模型 + 枚举
├── db/                            # SQLAlchemy 持久化（SQLite）
├── config/
│   ├── llm_tasks.yaml             # LLM 任务注册表
│   ├── research_policy.yaml       # 自动抓取/归一化/合成策略
│   ├── providers.yaml             # Provider 注册表
│   ├── prompt_templates/          # Prompt 模板（Jinja2 .md）
│   └── runtime_settings.json      # 运行时配置（.gitignore）
├── templates/                     # Jinja2 Markdown 模板
│   ├── source_note.md.j2          # 单篇来源笔记
│   └── research_index.md.j2       # 研究索引
├── ui/
│   ├── streamlit_app.py           # Streamlit 入口
│   ├── styles.py                  # 全局 CSS + Design Tokens
│   ├── api_client.py              # UI → API HTTP 客户端
│   ├── components/                # 统一组件库
│   │   ├── layout.py              # 页面头部 / Section / 状态展示
│   │   ├── status.py              # Badge 组件
│   │   ├── cards.py               # 统计卡片
│   │   ├── trace_panel.py         # Trace 面板
│   │   ├── source_cards.py        # 来源卡片
│   │   ├── forms.py               # 表单组件
│   │   └── task_queue_panel.py    # 队列面板
│   └── pages/
│       ├── 1_Research.py
│       ├── 2_Results.py
│       ├── 3_Report_Ingestion.py
│       ├── 4_External_Signals.py
│       ├── 9_Settings.py
│       ├── _research_helpers.py   # Research 纯函数
│       ├── _results_helpers.py    # Results 纯函数
│       └── _settings_helpers.py   # Settings 纯函数
├── tests/                         # 测试
├── start.sh                       # 一键启动
├── Makefile                       # 开发命令
└── pyproject.toml                 # 项目配置
```

## 测试

```bash
make test                               # 运行测试 + 覆盖率
python -m pytest                        # 全量测试
python -m pytest tests/ -q              # 简洁输出
python -m pytest tests/ -k "synthesis"  # 按关键词筛选

# UI 组件逻辑测试（不依赖 Streamlit 运行时）
python tests/test_ui_formatting_logic.py
python tests/test_trace_ui_formatting.py
python tests/test_research_page_logic.py
python tests/test_results_page_logic.py
python tests/test_settings_page_logic.py
python tests/test_state_components.py
```

## 开发命令

```bash
make install    # 安装依赖（含 dev）
make api        # 启动后端（热重载）
make ui         # 启动前端
make test       # 测试 + 覆盖率
make lint       # 代码检查
make fmt        # 格式化
make clean      # 清理缓存
```

## 设计原则

- **本地优先**：数据存储在本地 SQLite + Obsidian Vault，不依赖云服务
- **可降级**：LLM 不可用时规则 fallback 覆盖所有环节
- **可追溯**：每条事实都能追溯到原始来源和原文片段
- **可观测**：Research Trace 记录完整执行轨迹，产品化展示
- **低耦合**：AI Gateway 统一 LLM 调用，业务模块不直接依赖 Provider
- **不阻塞**：提取操作异步队列化，UI 始终响应
- **中英对照**：英文来源自动翻译，保留原文可追溯
- **安全**：API Key 不明文显示，Trace 自动脱敏敏感字段

## License

MIT
