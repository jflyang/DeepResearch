"""测试自动抓取策略 - S/A/B 自动抓取，C/D 默认跳过。"""

import pytest

from app.services.research_service import load_fetch_policy, load_normalization_policy, load_synthesis_policy


class TestFetchPolicyLevels:
    """auto_fetch include_levels 测试。"""

    def test_s_a_b_included(self):
        """S/A/B 在 include_levels 中。"""
        policy = load_fetch_policy()
        include = policy.get("include_levels", [])
        assert "S" in include
        assert "A" in include
        assert "B" in include

    def test_c_d_excluded(self):
        """C/D 不在 include_levels 中。"""
        policy = load_fetch_policy()
        include = policy.get("include_levels", [])
        assert "C" not in include
        assert "D" not in include

    def test_exclude_levels_has_c_d(self):
        """exclude_levels 包含 C 和 D。"""
        policy = load_fetch_policy()
        exclude = policy.get("exclude_levels", [])
        assert "C" in exclude
        assert "D" in exclude


class TestNormalizationPolicyLevels:
    """auto_normalization include_levels 测试。"""

    def test_s_a_b_included(self):
        """S/A/B 在 normalization include_levels 中。"""
        policy = load_normalization_policy()
        include = policy.get("include_levels", [])
        assert "S" in include
        assert "A" in include
        assert "B" in include

    def test_c_d_excluded(self):
        """C/D 不在 normalization include_levels 中。"""
        policy = load_normalization_policy()
        include = policy.get("include_levels", [])
        assert "C" not in include
        assert "D" not in include


class TestSynthesisPolicyLevels:
    """auto_synthesis include_levels 测试。"""

    def test_s_a_b_included(self):
        """S/A/B 在 synthesis include_levels 中。"""
        policy = load_synthesis_policy()
        include = policy.get("include_levels", [])
        assert "S" in include
        assert "A" in include
        assert "B" in include

    def test_c_d_excluded(self):
        """C/D 不在 synthesis include_levels 中。"""
        policy = load_synthesis_policy()
        include = policy.get("include_levels", [])
        assert "C" not in include
        assert "D" not in include
