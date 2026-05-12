# DeepResearch — 深度研究资料收集与合成工作台

本地优先的研究工作台。输入一个主题，自动完成搜索、抓取、归一化、去重、合成，最终输出一篇有来源引用的结构化研究文档到 Obsidian Vault。

支持三条研究路径：

1. **自动研究**：输入主题 → 搜索扩展 → 多源搜索 → 评分分类 → 自动抓取 S/A/B 级来源正文 → 内容归一化 → 跨来源去重 → LLM 合成研究文档 → 写入 Obsidian。
2. **外部报告导入**：粘贴 GPT / Perplexity / Claude 生成的研究报告 → 解析引用 → 抓取正文 → 补充检索书籍/论文 → 合成导出。
3. **手动合成**：在 Results 页面对已有来源手动触发"清洗并合成研究文档"。

## 核心特性

- 多源搜索：SearXNG、Open Library、Crossref、arXiv、Wikipedia、Tavily、Brave
- 智能评分：来源按 S/A/B/C/D 五级评估，自动过滤噪音
- 网页抓取：Crawlee 引擎 + Trafilatura，支持 HTTP / Browser / Adaptive 模式
- 内容归一化：LLM 将非结构化正文拆解为可追溯的结构化事实条目
- 跨来源去重：相同事实合并，来源冲突标记，多源确认提升可信度
- 研究合成：LLM 将去重后的事实组织为有叙事性的研究文档
- Obsidian 输出：生成 12 节结构化 index.md（概览、核心摘要、已确认事实、时间线、人物、地点、概念、故事点、图书、冲突、来源地图、下一步）
- 全程可降级：LLM 不可用时规则 fallback 覆盖所有环节
- 执行轨迹：Research Trace 记录每一步的 provider、耗时、输入输出

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
┌─ Auto Fetch（S/A/B 级）────────────────────────────────────────┐
│  Crawlee 抓取正文 → Trafilatura 提取 → LLM 文档分析             │
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
│  渲染 Markdown → 写入 Obsidian Vault index.md                   │
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

| Provider | 类型 | 需要 Key |
|----------|------|----------|
| SearXNG | 通用网页 | 否（自托管） |
| Wikipedia | 实体消歧 | 否 |
| Open Library | 图书 | 否 |
| Crossref | 论文 | 否 |
| arXiv | 论文 | 否 |
| Tavily | 通用网页 | 是 |
| Brave | 通用网页 | 是 |
| Google Books | 图书 | 可选 |

## UI 页面

| 页面 | 功能 |
|------|------|
| Research | 新建研究任务，配置模式/深度/自动抓取/自动合成，实时查看执行流程 |
| Results | 研究结果工作台：统计、筛选、分类浏览、导出、清洗合成、Trace |
| Report Ingestion | 导入外部 AI 研究报告，解析引用，补充检索 |
| Settings | Ollama / 云端 LLM / 搜索 Provider / Obsidian Vault 配置 |

## 内容归一化与研究合成

这是系统的核心差异化能力。传统研究工具只收集来源列表，DeepResearch 进一步将来源正文合成为可用的研究文档。

### 流程

1. **ContentNormalizationService**：对每篇已抓取正文，LLM 提取结构化事实条目（claim + evidence_text + 实体 + 置信度）
2. **CrossSourceDeduplicationService**：跨来源合并相同事实，标记冲突，多源确认提升可信度
3. **ResearchSynthesisService**：编排归一化 → 去重 → LLM 合成，生成 SynthesizedResearchDocument
4. **render_synthesized_index**：渲染为 Obsidian 兼容的 12 节 Markdown

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
| document_summary | analysis | 正文摘要与实体提取 |
| entity_extraction | analysis | 实体提取 |
| content_normalization | synthesis | 正文归一化为结构化事实 |
| cross_source_deduplication | synthesis | 跨来源去重与冲突检测 |
| research_synthesis | synthesis | 研究文档合成 |
| report_understanding | ingestion | 外部报告理解 |
| report_reference_extraction | ingestion | 报告引用提取 |

## API 端点

### 研究任务

```
POST   /research/tasks                    创建任务
POST   /research/tasks/{id}/run           执行研究
GET    /research/tasks/{id}               任务状态
GET    /research/tasks/{id}/sources       来源列表
POST   /research/tasks/{id}/synthesize    执行合成（归一化→去重→合成→写index）
POST   /research/tasks/{id}/normalize     仅归一化
GET    /research/tasks/{id}/synthesis     合成状态
POST   /research/tasks/{id}/export-index  导出研究索引
GET    /research/tasks/{id}/trace         执行轨迹
GET    /research/tasks/{id}/trace/summary 轨迹摘要
GET    /research/tasks/{id}/trace/llm     LLM 使用详情
```

### 任务管理

```
GET    /research/tasks                    任务列表
PATCH  /research/tasks/{id}              重命名
DELETE /research/tasks/{id}              删除
POST   /research/tasks/{id}/clone        复制
POST   /research/tasks/{id}/rerun        重新运行
```

### 报告导入

```
POST   /research/import-report            创建导入任务
POST   /research/import-report/{id}/parse 解析引用
POST   /research/import-report/{id}/run   执行抓取
```

## 目录结构

```
DeepResearch/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── ai/                        # AI Gateway（gateway/router/tasks/prompts/parser/schemas）
│   ├── tracing/                   # Research Trace（recorder/models/llm_registry）
│   ├── crawlers/                  # Crawlee 网页抓取（crawlee_service/relevance_filter/content_extractor）
│   ├── services/                  # LLM 增强服务
│   │   ├── content_normalization_service.py   # 内容归一化
│   │   ├── cross_source_deduplication_service.py  # 跨来源去重
│   │   ├── research_synthesis_service.py      # 研究合成编排
│   │   ├── research_service.py                # 合成 API 入口
│   │   ├── markdown_service.py                # 合成文档 Markdown 渲染
│   │   ├── document_analysis_service.py       # 文档分析
│   │   ├── topic_understanding_service.py     # 主题理解
│   │   └── report_*.py                        # 报告导入相关
│   ├── providers/llm/             # LLM Provider（ollama/openai_compatible/mock）
│   ├── core/                      # 服务注册 / Feature Flags
│   └── vault/                     # Vault Workspace
├── api/                           # HTTP 路由（research/export/sources/tasks）
├── services/                      # 核心业务编排（research/scoring/dedupe/markdown/queue）
├── providers/search/              # 搜索 Provider（tavily/brave/searxng/open_library/crossref/arxiv/wikipedia）
├── models/                        # Pydantic 数据模型 + 枚举
├── db/                            # SQLAlchemy 持久化
├── config/
│   ├── llm_tasks.yaml             # LLM 任务注册表
│   ├── research_policy.yaml       # 自动抓取/归一化/合成策略
│   ├── prompt_templates/          # Prompt 模板（Jinja2）
│   ├── providers.yaml             # 服务注册表
│   └── runtime_settings.json      # 运行时配置（.gitignore）
├── templates/                     # Jinja2 Markdown 模板
├── ui/
│   └── pages/                     # Streamlit 页面
├── tests/                         # 1500+ 测试
├── start.sh                       # 一键启动
└── pyproject.toml
```

## 测试

```bash
python -m pytest                    # 全量测试（~1570 tests）
python -m pytest tests/ -q          # 简洁输出
python -m pytest tests/ -k "synthesis"  # 按关键词筛选
python -m pytest --cov=app --cov=services --cov=providers  # 覆盖率
```

## 设计原则

- **本地优先**：数据存储在本地 SQLite + Obsidian Vault，不依赖云服务
- **可降级**：LLM 不可用时规则 fallback 覆盖所有环节
- **可追溯**：每条事实都能追溯到原始来源和原文片段
- **可观测**：Research Trace 记录完整执行轨迹
- **低耦合**：AI Gateway 统一 LLM 调用，业务模块不直接依赖 Provider
- **不覆盖原文**：Obsidian 笔记保留英文原文，中文摘要在前
- **安全**：API Key 不明文显示，Trace 自动脱敏

## License

MIT
