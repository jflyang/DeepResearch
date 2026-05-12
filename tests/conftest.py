"""测试公共 fixtures。"""

import pytest

from providers.llm.mock import MockLLMProvider
from services.scoring_service import _reset_rules_cache


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture(autouse=True)
def clear_scoring_cache():
    """每个测试前清除评分规则缓存。"""
    _reset_rules_cache()
    yield
    _reset_rules_cache()
