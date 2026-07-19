"""memo_id_display の short_memo_id / resolve_memo_id_prefix 単体テスト
(Issue #276)。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.memo_id_display import (
    SHORT_MEMO_ID_LENGTH,
    resolve_memo_id_prefix,
    short_memo_id,
)


class TestShortMemoId:
    """short_memo_id の挙動。"""

    def test_uuid4_first_6(self) -> None:
        """典型ケース: 36 文字の UUID4 → 6 文字 + …。"""
        full = "a3b9f1c2-1234-5678-9abc-def012345678"
        assert short_memo_id(full) == "a3b9f1…"

    def test_id(self) -> None:
        """6 文字以下なら省略マーカーは付かない。"""
        assert short_memo_id("abc") == "abc"
        assert short_memo_id("abcdef") == "abcdef"  # ちょうど 6 文字

    def test_7_more(self) -> None:
        """7 文字以上から省略マーカーが付く。"""
        assert short_memo_id("abcdefg") == "abcdef…"

    def test_empty_string_empty_string(self) -> None:
        """空文字は空文字のまま。"""
        assert short_memo_id("") == ""

    def test_short_memo_id_length_6(self) -> None:
        """定数が他のコードベースから参照される可能性に備えて固定。"""
        assert SHORT_MEMO_ID_LENGTH == 6


class TestResolveMemoIdPrefix:
    """resolve_memo_id_prefix の挙動。"""

    def test_returns_full_uuid_exact_match(self) -> None:
        """full uuid は exact match でそのまま返る。"""
        ids = ["a3b9f1c2-aaaa", "b7c2d3e4-bbbb"]
        resolved, amb = resolve_memo_id_prefix("a3b9f1c2-aaaa", ids)
        assert resolved == "a3b9f1c2-aaaa"
        assert amb == []

    def test_returns_prefix_one_full_id(self) -> None:
        """短い prefix が 1 件に確定するなら full id を返す。"""
        ids = ["a3b9f1c2-aaaa", "b7c2d3e4-bbbb"]
        resolved, amb = resolve_memo_id_prefix("a3b9f1", ids)
        assert resolved == "a3b9f1c2-aaaa"
        assert amb == []

    def test_prefix_multiple_matches_ambiguous_column(self) -> None:
        """prefix が複数に一致するなら ambiguous に列挙。"""
        ids = ["a3b9f1-one", "a3b9f1-two"]
        resolved, amb = resolve_memo_id_prefix("a3b9f1", ids)
        assert resolved is None
        assert set(amb) == set(ids)

    def test_does_not_match_empty_none(self) -> None:
        """どれにも一致しないなら 両方とも空 None。"""
        ids = ["aaa", "bbb"]
        resolved, amb = resolve_memo_id_prefix("zzz", ids)
        assert resolved is None
        assert amb == []

    def test_last_trim(self) -> None:
        """LLM が表示形 'a3b9f1…' をそのまま投げ返してきても解決できる。"""
        ids = ["a3b9f1c2-aaaa"]
        resolved, _ = resolve_memo_id_prefix("a3b9f1…", ids)
        assert resolved == "a3b9f1c2-aaaa"

    def test_empty_prefix_none(self) -> None:
        """空 prefix は None。"""
        resolved, amb = resolve_memo_id_prefix("", ["aaa"])
        assert resolved is None
        assert amb == []
