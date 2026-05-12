"""测试文件驱动的研究合成服务。"""

import tempfile
from pathlib import Path

import pytest

from app.services.file_based_synthesis_service import (
    list_source_files,
    read_source_file,
    synthesize_from_source_files,
)


# === Fixtures ===


def _create_source_file(sources_dir: Path, filename: str, content: str) -> Path:
    """在 sources/ 目录创建一个 .md 文件。"""
    path = sources_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


_SAMPLE_SOURCE_1 = """---
title: "Apple 创立故事"
url: "https://example.com/apple-founding"
source_level: "S"
source_type: "news"
topic: "Apple 发展史"
people: ["Steve Jobs", "Steve Wozniak"]
places: ["Cupertino"]
---

# 中文摘要

Apple 于 1976 年由 Steve Jobs 和 Steve Wozniak 在车库创立。

# 为什么值得看

一手资料，详细描述了创立过程。

# 关键事实

- 1976 年 Apple 在加州车库成立
- Steve Jobs 和 Steve Wozniak 是联合创始人
- 第一款产品是 Apple I 电脑

# 可用于播客的故事点

- 两个大学辍学生在车库里创造了改变世界的公司
- Jobs 曾被自己创立的公司开除

# 关键摘录

> We started in a garage, and we didn't have much money.

# 重点名词

- [[Apple I]]
- [[Homebrew Computer Club]]

# 正文

Apple Computer Company was founded on April 1, 1976, by Steve Jobs, Steve Wozniak, and Ronald Wayne...
"""

_SAMPLE_SOURCE_2 = """---
title: "iPhone 发布会"
url: "https://example.com/iphone-launch"
source_level: "A"
source_type: "news"
topic: "Apple 发展史"
people: ["Steve Jobs"]
places: ["San Francisco"]
---

# 中文摘要

2007 年 Steve Jobs 在 Macworld 发布了 iPhone，彻底改变了手机行业。

# 为什么值得看

iPhone 发布是 Apple 历史上最重要的时刻之一。

# 关键事实

- 2007 年 1 月 iPhone 在 Macworld 发布
- Jobs 称之为"革命性产品"
- 首批 iPhone 6 月上市

# 可用于播客的故事点

- Jobs 在台上说"今天 Apple 要重新发明手机"

# 关键摘录

> Today Apple is going to reinvent the phone.

# 正文

On January 9, 2007, Steve Jobs took the stage at Macworld...
"""


# === Tests ===


class TestListSourceFiles:
    """列出 sources/ 目录下的 .md 文件。"""

    def test_lists_md_files(self, tmp_path):
        """正确列出 .md 文件。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", "# test")
        _create_source_file(sources_dir, "source2.md", "# test2")
        (sources_dir / "not_md.txt").write_text("ignore")

        files = list_source_files(str(vault), "Apple")
        assert len(files) == 2
        assert all(f.suffix == ".md" for f in files)

    def test_empty_dir_returns_empty(self, tmp_path):
        """空目录返回空列表。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple" / "sources"
        sources_dir.mkdir(parents=True)

        files = list_source_files(str(vault), "Apple")
        assert files == []

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        """不存在的目录返回空列表。"""
        files = list_source_files(str(tmp_path / "nonexistent"), "Apple")
        assert files == []


class TestReadSourceFile:
    """读取单个 source .md 文件。"""

    def test_parses_frontmatter(self, tmp_path):
        """正确解析 frontmatter。"""
        path = tmp_path / "test.md"
        path.write_text(_SAMPLE_SOURCE_1, encoding="utf-8")

        data = read_source_file(path)
        assert data["title"] == "Apple 创立故事"
        assert data["url"] == "https://example.com/apple-founding"
        assert data["source_level"] == "S"
        assert "Steve Jobs" in data["people"]

    def test_parses_key_points(self, tmp_path):
        """正确提取关键事实。"""
        path = tmp_path / "test.md"
        path.write_text(_SAMPLE_SOURCE_1, encoding="utf-8")

        data = read_source_file(path)
        assert len(data["key_points"]) == 3
        assert "1976" in data["key_points"][0]

    def test_parses_quotes(self, tmp_path):
        """正确提取引用。"""
        path = tmp_path / "test.md"
        path.write_text(_SAMPLE_SOURCE_1, encoding="utf-8")

        data = read_source_file(path)
        assert len(data["key_quotes"]) >= 1
        assert "garage" in data["key_quotes"][0]

    def test_parses_story_points(self, tmp_path):
        """正确提取故事点。"""
        path = tmp_path / "test.md"
        path.write_text(_SAMPLE_SOURCE_1, encoding="utf-8")

        data = read_source_file(path)
        assert len(data["story_points"]) >= 1


class TestSynthesizeFromSourceFiles:
    """从 sources/ 合成 index.md。"""

    def test_generates_index(self, tmp_path):
        """成功生成 index.md。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)
        _create_source_file(sources_dir, "source2.md", _SAMPLE_SOURCE_2)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")

        assert result["success"] is True
        assert result["source_count"] == 2
        assert result["index_path"] != ""

        # 验证 index.md 存在
        index_path = Path(result["index_path"])
        assert index_path.exists()

    def test_index_contains_research_overview(self, tmp_path):
        """index.md 包含研究概览。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")
        index_content = Path(result["index_path"]).read_text(encoding="utf-8")

        assert "研究概览" in index_content
        assert "Apple 发展史" in index_content

    def test_index_contains_key_facts(self, tmp_path):
        """index.md 包含关键事实。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)
        _create_source_file(sources_dir, "source2.md", _SAMPLE_SOURCE_2)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")
        index_content = Path(result["index_path"]).read_text(encoding="utf-8")

        assert "1976" in index_content
        assert "iPhone" in index_content

    def test_index_contains_people(self, tmp_path):
        """index.md 包含相关人物。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")
        index_content = Path(result["index_path"]).read_text(encoding="utf-8")

        assert "Steve Jobs" in index_content

    def test_index_contains_source_map(self, tmp_path):
        """index.md 包含来源地图。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")
        index_content = Path(result["index_path"]).read_text(encoding="utf-8")

        assert "来源地图" in index_content
        assert "source1.md" in index_content

    def test_no_sources_returns_error(self, tmp_path):
        """没有 source 文件时返回错误。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Empty" / "sources"
        sources_dir.mkdir(parents=True)

        result = synthesize_from_source_files(str(vault), "Empty")

        assert result["success"] is False
        assert "没有" in result["error"]

    def test_index_has_frontmatter(self, tmp_path):
        """index.md 有 YAML frontmatter。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")
        index_content = Path(result["index_path"]).read_text(encoding="utf-8")

        assert index_content.startswith("---\n")
        assert "synthesis: true" in index_content

    def test_timeline_extracted(self, tmp_path):
        """index.md 包含时间线。"""
        vault = tmp_path / "vault"
        sources_dir = vault / "Research" / "Apple 发展史" / "sources"
        sources_dir.mkdir(parents=True)
        _create_source_file(sources_dir, "source1.md", _SAMPLE_SOURCE_1)
        _create_source_file(sources_dir, "source2.md", _SAMPLE_SOURCE_2)

        result = synthesize_from_source_files(str(vault), "Apple 发展史")
        index_content = Path(result["index_path"]).read_text(encoding="utf-8")

        assert "时间线" in index_content
        assert "1976" in index_content
        assert "2007" in index_content
