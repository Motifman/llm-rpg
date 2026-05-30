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

    def test_uuid4_は先頭_6_文字_と_省略マーカーになる(self) -> None:
        """典型ケース: 36 文字の UUID4 → 6 文字 + …。"""
        full = "a3b9f1c2-1234-5678-9abc-def012345678"
        assert short_memo_id(full) == "a3b9f1…"

    def test_既に短い_id_は_そのまま_省略マーカーなし(self) -> None:
        """6 文字以下なら省略マーカーは付かない。"""
        assert short_memo_id("abc") == "abc"
        assert short_memo_id("abcdef") == "abcdef"  # ちょうど 6 文字

    def test_7_文字以上から省略マーカーが付く(self) -> None:
        assert short_memo_id("abcdefg") == "abcdef…"

    def test_空文字は空文字のまま(self) -> None:
        assert short_memo_id("") == ""

    def test_SHORT_MEMO_ID_LENGTH_定数は_6(self) -> None:
        """定数が他のコードベースから参照される可能性に備えて固定。"""
        assert SHORT_MEMO_ID_LENGTH == 6


class TestResolveMemoIdPrefix:
    """resolve_memo_id_prefix の挙動。"""

    def test_full_uuid_は_exact_match_でそのまま返る(self) -> None:
        ids = ["a3b9f1c2-aaaa", "b7c2d3e4-bbbb"]
        resolved, amb = resolve_memo_id_prefix("a3b9f1c2-aaaa", ids)
        assert resolved == "a3b9f1c2-aaaa"
        assert amb == []

    def test_短い_prefix_が_1_件に確定するなら_full_id_を返す(self) -> None:
        ids = ["a3b9f1c2-aaaa", "b7c2d3e4-bbbb"]
        resolved, amb = resolve_memo_id_prefix("a3b9f1", ids)
        assert resolved == "a3b9f1c2-aaaa"
        assert amb == []

    def test_prefix_が複数に一致するなら_ambiguous_に列挙(self) -> None:
        ids = ["a3b9f1-one", "a3b9f1-two"]
        resolved, amb = resolve_memo_id_prefix("a3b9f1", ids)
        assert resolved is None
        assert set(amb) == set(ids)

    def test_どれにも一致しないなら_両方とも空_None(self) -> None:
        ids = ["aaa", "bbb"]
        resolved, amb = resolve_memo_id_prefix("zzz", ids)
        assert resolved is None
        assert amb == []

    def test_末尾の省略マーカー_は_trim_される(self) -> None:
        """LLM が表示形 'a3b9f1…' をそのまま投げ返してきても解決できる。"""
        ids = ["a3b9f1c2-aaaa"]
        resolved, _ = resolve_memo_id_prefix("a3b9f1…", ids)
        assert resolved == "a3b9f1c2-aaaa"

    def test_空_prefix_は_None(self) -> None:
        resolved, amb = resolve_memo_id_prefix("", ["aaa"])
        assert resolved is None
        assert amb == []
