#!/usr/bin/env python3
"""手动测试局域网 Ollama 连接 - 不依赖 FastAPI。"""

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

import os

from app.providers.llm.base import LLMRequest
from app.providers.llm.ollama import OllamaProvider, OllamaProviderError


def _get_config() -> tuple[str, str]:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    model = os.environ.get("OLLAMA_DEFAULT_MODEL", "qwen3:8b").strip()
    return base_url, model


def _print_header(base_url: str, model: str) -> None:
    print("=" * 60)
    print("  Ollama 连接测试")
    print("=" * 60)
    print(f"  Base URL : {base_url}")
    print(f"  Model    : {model}")
    print("-" * 60)


def _print_troubleshooting(base_url: str, model: str) -> None:
    print("\n❌ 连接失败，请检查：")
    print(f"  1. OLLAMA_BASE_URL 是否正确: {base_url}")
    print(f"  2. 局域网是否能访问该地址（ping / curl {base_url}/api/tags）")
    print("  3. Ollama 服务是否已启动（ollama serve）")
    print(f"  4. 模型是否已 pull（ollama pull {model}）")
    print("  5. 防火墙是否放行 11434 端口")


async def main() -> None:
    base_url, model = _get_config()
    _print_header(base_url, model)

    provider = OllamaProvider(base_url=base_url)

    # 1. Health check
    print("\n[1/2] Health Check...")
    health = await provider.health_check()
    print(f"  reachable  : {health.reachable}")
    print(f"  latency_ms : {health.latency_ms}")

    if not health.reachable:
        print(f"  error      : {health.error}")
        _print_troubleshooting(base_url, model)
        sys.exit(1)

    print("  ✅ Ollama 可达")

    # 2. Generate test
    print(f"\n[2/2] Generate 测试 (model={model})...")
    request = LLMRequest(
        model=model,
        user_prompt="用一句话回答：你可以为研究资料收集器做什么？",
        max_output_tokens=64,
        timeout_seconds=60,
    )

    try:
        response = await provider.generate(request)
    except OllamaProviderError as e:
        print(f"  ❌ Generate 失败: {e.message}")
        if "404" in str(e.status_code or ""):
            print(f"  → 模型可能未 pull，请执行: ollama pull {model}")
        _print_troubleshooting(base_url, model)
        sys.exit(1)

    text_preview = response.text[:200].replace("\n", " ")
    print(f"  model       : {response.model}")
    print(f"  latency_ms  : {response.latency_ms}")
    print(f"  output_chars: {response.output_chars}")
    print(f"  response    : {text_preview}")
    print("\n  ✅ Generate 成功")

    print("\n" + "=" * 60)
    print("  所有测试通过 ✅")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
