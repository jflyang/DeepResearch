你是一个研究助手。请为以下来源生成简短的中文阅读理由（reason_to_read）。

研究主题：{{ topic }}

来源列表：
{% for source in sources %}
- 标题：{{ source.title }}
  URL：{{ source.url }}
  等级：{{ source.level }}
  类型：{{ source.type }}
  摘要：{{ source.snippet }}
{% endfor %}

请为每个来源生成一句话的阅读理由，说明为什么研究者应该阅读这个来源。

返回 JSON 格式：
```json
{
  "reasons": [
    {"url": "来源URL", "reason": "一句话阅读理由"}
  ]
}
```

要求：
- 每条理由不超过 50 字
- 用中文
- 突出该来源对研究主题的独特价值
- 不要重复来源标题
