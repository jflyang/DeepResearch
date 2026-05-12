"""查询扩展服务测试。"""

import pytest

from models.enums import TaskMode
from services.query_expansion_service import ExpandedQuery, expand_queries


class TestPersonMode:
    def test_generates_childhood(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON)
        queries = [r.query for r in results]
        assert "Elon Musk childhood" in queries

    def test_generates_biography(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON)
        queries = [r.query for r in results]
        assert "Elon Musk biography" in queries

    def test_generates_interview(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON)
        queries = [r.query for r in results]
        assert "Elon Musk interview" in queries

    def test_generates_early_life(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON)
        queries = [r.query for r in results]
        assert "Elon Musk early life" in queries

    def test_source_hint_is_web(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_books=False)
        for r in results:
            assert r.source_hint == "web"


class TestCompanyMode:
    def test_generates_founding(self):
        results = expand_queries("Tesla", mode=TaskMode.COMPANY)
        queries = [r.query for r in results]
        assert "Tesla founding story" in queries

    def test_generates_early_history(self):
        results = expand_queries("Tesla", mode=TaskMode.COMPANY)
        queries = [r.query for r in results]
        assert "Tesla early history" in queries

    def test_generates_founders(self):
        results = expand_queries("Tesla", mode=TaskMode.COMPANY)
        queries = [r.query for r in results]
        assert "Tesla founders" in queries

    def test_generates_failure(self):
        results = expand_queries("Tesla", mode=TaskMode.COMPANY)
        queries = [r.query for r in results]
        assert "Tesla failure" in queries


class TestEventMode:
    def test_generates_timeline(self):
        results = expand_queries("FTX collapse", mode=TaskMode.EVENT)
        queries = [r.query for r in results]
        assert "FTX collapse timeline" in queries

    def test_generates_controversy(self):
        results = expand_queries("FTX collapse", mode=TaskMode.EVENT)
        queries = [r.query for r in results]
        assert "FTX collapse controversy" in queries

    def test_generates_lawsuit(self):
        results = expand_queries("FTX collapse", mode=TaskMode.EVENT)
        queries = [r.query for r in results]
        assert "FTX collapse lawsuit" in queries


class TestConceptMode:
    def test_generates_origin(self):
        results = expand_queries("quantum computing", mode=TaskMode.CONCEPT)
        queries = [r.query for r in results]
        assert "quantum computing origin" in queries

    def test_generates_paper(self):
        results = expand_queries("quantum computing", mode=TaskMode.CONCEPT)
        queries = [r.query for r in results]
        assert "quantum computing paper" in queries


class TestIncludeBooks:
    def test_adds_book_queries(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_books=True)
        queries = [r.query for r in results]
        assert "Elon Musk biography book" in queries
        assert "Elon Musk book" in queries
        assert "Elon Musk memoir" in queries

    def test_book_source_hint(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_books=True)
        book_results = [r for r in results if r.source_hint == "book"]
        assert len(book_results) >= 3

    def test_no_book_queries_when_disabled(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_books=False)
        queries = [r.query for r in results]
        assert "Elon Musk biography book" not in queries
        assert "Elon Musk book" not in queries


class TestIncludeGossip:
    def test_adds_gossip_queries(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_gossip=True)
        queries = [r.query for r in results]
        assert "Elon Musk rumor" in queries
        assert "Elon Musk personal life" in queries

    def test_no_gossip_when_disabled(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_gossip=False)
        queries = [r.query for r in results]
        assert "Elon Musk rumor" not in queries


class TestIncludeVideo:
    def test_adds_video_queries(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_video=True)
        queries = [r.query for r in results]
        assert "Elon Musk documentary" in queries
        assert "Elon Musk interview video" in queries

    def test_video_source_hint(self):
        results = expand_queries("Elon Musk", mode=TaskMode.PERSON, include_video=True)
        video_results = [r for r in results if r.source_hint == "video"]
        assert len(video_results) >= 2


class TestDeduplication:
    def test_no_duplicate_queries(self):
        # controversy 出现在 event 模板和 gossip 模板中
        results = expand_queries("FTX", mode=TaskMode.EVENT, include_gossip=True)
        queries = [r.query.lower() for r in results]
        assert len(queries) == len(set(queries))

    def test_case_insensitive_dedup(self):
        results = expand_queries("Test", mode=TaskMode.CONCEPT, include_gossip=True)
        queries_lower = [r.query.lower() for r in results]
        assert len(queries_lower) == len(set(queries_lower))


class TestOutputStructure:
    def test_returns_expanded_query_instances(self):
        results = expand_queries("test", mode=TaskMode.AUTO)
        assert all(isinstance(r, ExpandedQuery) for r in results)

    def test_priority_increments(self):
        results = expand_queries("test", mode=TaskMode.CONCEPT)
        priorities = [r.priority for r in results]
        assert priorities == list(range(1, len(results) + 1))

    def test_round_number_passed(self):
        results = expand_queries("test", mode=TaskMode.AUTO, round_number=3)
        for r in results:
            assert r.round == 3

    def test_non_empty_results(self):
        for mode in TaskMode:
            results = expand_queries("topic", mode=mode)
            assert len(results) > 0, f"No results for mode {mode}"
