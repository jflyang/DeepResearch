你是一个研究助手。请根据以下研究来源信息，生成一段研究概览。

研究主题：{{ topic }}
研究模式：{{ mode }}
来源总数：{{ total_sources }}
高质量来源 (S/A)：{{ high_quality_count }}

高质量来源列表：
{% for source in top_sources %}
- [{{ source.level }}] {{ source.title }}
  理由：{{ source.reason }}
{% endfor %}

请生成一段 200-400 字的中文研究概览，包括：
1. 研究主题的简要背景
2. 本次研究发现的主要信息来源类型
3. 值得深入阅读的方向建议

直接输出 Markdown 格式，不要包裹在代码块中。以"## 研究概览"开头。
