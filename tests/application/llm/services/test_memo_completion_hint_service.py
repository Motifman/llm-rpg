"""MemoCompletionHintService の挙動テスト (Issue #188 Phase 1c、#1628 でメモ帳のやることに替えた)。"""

import pytest

from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    DEFAULT_SIMILARITY_THRESHOLD,
    MemoCompletionHint,
    MemoCompletionHintService,
    PendingTodo,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

_ADA = BeingId("ada")


def _todo(content: str, index: int = 1) -> PendingTodo:
    return PendingTodo(id=f"3f2a7b9c-1d2e-4f00-8a00-00000000000{index}", content=content, handle=f"m_{index}")


def _service(
    todos: list[PendingTodo],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> MemoCompletionHintService:
    return MemoCompletionHintService(
        pending_todos=lambda being_id: todos,
        similarity_threshold=similarity_threshold,
    )


class TestMemoCompletionHintServiceConstruction:
    """MemoCompletionHintService コンストラクタの引数バリデーション挙動。"""

    def test_non_callable_pending_todos_raises_type_error(self) -> None:
        """pending_todos に呼べないものを渡すと TypeError を投げる。"""
        with pytest.raises(TypeError, match="pending_todos"):
            MemoCompletionHintService(pending_todos="not-callable")  # type: ignore[arg-type]

    def test_threshold_out_of_range_raises_value_error(self) -> None:
        """similarity_threshold は [0.0, 1.0] 範囲外なら ValueError。"""
        with pytest.raises(ValueError):
            _service([], similarity_threshold=1.5)
        with pytest.raises(ValueError):
            _service([], similarity_threshold=-0.1)


class TestMemoCompletionHintDetect:
    """detect の hint 検出挙動。"""

    def test_no_todos_returns_no_hint(self) -> None:
        """やることが無ければ hint なし (None)。"""
        assert _service([]).detect(_ADA, "act", "res").hint is None

    def test_todos_below_threshold_return_no_hint(self) -> None:
        """全てのやることが閾値未満なら hint なし。"""
        service = _service([_todo("金庫室で扉固定スイッチを押す")])

        result = service.detect(_ADA, action_summary="speak to カイト", result_summary="話しかけた").hint

        assert result is None

    def test_todo_above_threshold_returns_hint(self) -> None:
        """やることの文と行動 / 結果が十分に重なれば、そのやることの hint を返す。"""
        todo = _todo("金庫室で扉固定スイッチを押す")
        service = _service([todo], similarity_threshold=0.3)

        result = service.detect(_ADA, action_summary="金庫室で扉固定スイッチを押す", result_summary="press 成功").hint

        assert result is not None
        assert result.memo == todo
        assert result.similarity >= 0.3

    def test_most_overlapping_todo_wins_among_several(self) -> None:
        """複数候補があれば最も重なるやることを返す。"""
        target = _todo("金庫室で扉固定スイッチを押す", index=2)
        service = _service([_todo("リンと合流する"), target], similarity_threshold=0.3)

        result = service.detect(
            _ADA, action_summary="金庫室で扉固定スイッチを押した", result_summary="latch engaged"
        ).hint

        assert result is not None
        assert result.memo == target


class TestMemoCompletionHintAugmentResultSummary:
    """augment_result_summary の整形挙動。"""

    def test_without_hint_result_summary_is_unchanged(self) -> None:
        """やることが無ければ augment しても元のまま。"""
        assert _service([]).augment_result_summary(_ADA, "press latch", "press 成功") == "press 成功"

    def test_with_hint_result_summary_gets_hint_appended(self) -> None:
        """閾値以上のやることがあれば result_summary 末尾に [hint] が付き、memo の remove で消す案内を含む。"""
        service = _service([_todo("金庫室で扉固定スイッチを押す")], similarity_threshold=0.3)

        augmented = service.augment_result_summary(_ADA, "金庫室で扉固定スイッチを押す", "press 成功")

        assert augmented.startswith("press 成功")
        assert "[hint]" in augmented
        assert "memo の remove" in augmented


class TestMemoCompletionHintToHintText:
    """MemoCompletionHint.to_hint_text の整形。"""

    def test_hint_text_shows_handle_and_measure(self) -> None:
        """LLM 向け hint 文にやることの呼び名と類似度が出て、内部 ID は出ない。"""
        todo = _todo("金庫室で扉固定スイッチを押す")

        text = MemoCompletionHint(memo=todo, similarity=0.67).to_hint_text()

        assert "(m_1)" in text
        assert "0.67" in text
        assert todo.id not in text


def test_default_similarity_threshold() -> None:
    """既定閾値が [0,1] 範囲内であること。"""
    assert 0.0 <= DEFAULT_SIMILARITY_THRESHOLD <= 1.0


class TestHintForMemoBookTodos:
    """メモ帳のやること (#1628) に済んだかを知らせ、消し方は引数 memo で示すことを保証する。"""

    def test_matching_todo_gets_a_hint_with_its_handle(self) -> None:
        """行動と結果がやることの文を含めば、そのやることの呼び名と、memo の remove で消す案内を返す。"""
        todo = PendingTodo(id="3f2a7b9c-1d2e-4f00-8a00-000000000001", content="事務所で鍵を取る", handle="m_3f2a7b")

        hint = _service([todo]).detect(_ADA, "事務所で鍵を取る", "鍵を手に入れた").hint

        assert hint is not None and hint.memo == todo
        assert hint.to_hint_text() == (
            "\n\n[hint] やること「事務所で鍵を取る」(m_3f2a7b) は済んだかもしれません (類似度 1.00)。"
            "済んだなら memo の remove で消してください。"
        )

    def test_unrelated_todo_gets_no_hint(self) -> None:
        """行動と結果がやることと重ならなければ、知らせない。"""
        todo = PendingTodo(id="3f2a7b9c-1d2e-4f00-8a00-000000000001", content="事務所で鍵を取る", handle="m_3f2a7b")

        assert _service([todo]).detect(_ADA, "井戸で水を汲む", "水が汲めた").hint is None

    def test_pending_todos_are_asked_for_the_calling_being(self) -> None:
        """やることは、detect に渡した Being について引く。"""
        asked: list[BeingId] = []
        service = MemoCompletionHintService(pending_todos=lambda being_id: asked.append(being_id) or [])

        service.detect(_ADA, "act", "res")

        assert asked == [_ADA]

    def test_excluded_todo_gets_no_hint(self) -> None:
        """問わないと渡したやることは、行動と重なっても知らせない。"""
        todo = PendingTodo(id="3f2a7b9c-1d2e-4f00-8a00-000000000001", content="事務所で鍵を取る", handle="m_3f2a7b")

        detection = _service([todo]).detect(
            _ADA, "事務所で鍵を取る", "鍵を手に入れた", excluded_ids={todo.id}
        )

        assert detection.hint is None
