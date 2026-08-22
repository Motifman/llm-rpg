"""MemoCompletionHintService の挙動テスト (Issue #188 Phase 1c)。

呼び出し側が BeingId を渡す構成。memo_store への being_id 経由追加・参照を検証。
"""

import pytest

from ai_rpg_world.application.llm.services.in_memory_memo_store import InMemoryMemoStore
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    DEFAULT_SIMILARITY_THRESHOLD,
    MemoCompletionHint,
    MemoCompletionHintService,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from tests.application.llm._memo_being_test_helpers import (
    MemoBeingTestSetup,
    make_memo_being_setup,
)


@pytest.fixture
def being_setup() -> MemoBeingTestSetup:
    setup = make_memo_being_setup()
    setup.provision(1)
    return setup


def _make_hint_service(
    being_setup: MemoBeingTestSetup,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> MemoCompletionHintService:
    """HintService を組み立てる helper。"""
    return MemoCompletionHintService(
        memo_store=being_setup.memo_store,
        similarity_threshold=similarity_threshold,
    )


class TestMemoCompletionHintServiceConstruction:
    """MemoCompletionHintService コンストラクタの引数バリデーション挙動。"""

    def test_memo_store_memo_repository_raises_type_error(self) -> None:
        """memo_store が MemoRepository 実装でない場合は TypeError。"""
        with pytest.raises(TypeError, match="memo_store"):
            MemoCompletionHintService(memo_store="not-a-store")  # type: ignore[arg-type]

    def test_threshold_raises_value_error(self) -> None:
        """similarity_threshold は [0.0, 1.0] 範囲外なら ValueError。"""
        store = InMemoryMemoStore()
        with pytest.raises(ValueError):
            MemoCompletionHintService(memo_store=store, similarity_threshold=1.5)
        with pytest.raises(ValueError):
            MemoCompletionHintService(memo_store=store, similarity_threshold=-0.1)


class TestMemoCompletionHintDetect:
    """detect の hint 検出挙動。"""

    def test_returns_none_memo(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """memo_store が空なら hint なし (None)。"""
        service = _make_hint_service(being_setup)
        being_id = being_setup.being_id_for(1)
        assert service.detect(being_id, "act", "res") is None

    def test_returns_none_value_below(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """全 memo が閾値未満なら hint なし。"""
        being_id = being_setup.being_id_for(1)
        being_setup.memo_store.add_by_being(
            being_id, "金庫室で扉固定スイッチを押す"
        )
        service = _make_hint_service(being_setup)
        # 全く無関係な行動
        result = service.detect(
            being_id,
            action_summary="speak to カイト",
            result_summary="話しかけた",
        )
        assert result is None

    def test_returns_value_more_hint(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """memo content と action/result が十分に類似していれば hint。"""
        being_id = being_setup.being_id_for(1)
        memo_id = being_setup.memo_store.add_by_being(
            being_id, "金庫室で扉固定スイッチを押す"
        )
        service = _make_hint_service(being_setup, similarity_threshold=0.3)
        result = service.detect(
            being_id,
            action_summary="金庫室で扉固定スイッチを押す",
            result_summary="press 成功",
        )
        assert result is not None
        assert result.memo.id == memo_id
        assert result.similarity >= 0.3

    def test_multiple_memo(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """複数候補があれば最高 ratio の memo を返す。"""
        store = being_setup.memo_store
        being_id = being_setup.being_id_for(1)
        store.add_by_being(being_id, "リンと合流する")
        target_id = store.add_by_being(being_id, "金庫室で扉固定スイッチを押す")
        service = _make_hint_service(being_setup, similarity_threshold=0.3)
        result = service.detect(
            being_id,
            action_summary="金庫室で扉固定スイッチを押した",
            result_summary="latch engaged",
        )
        assert result is not None
        assert result.memo.id == target_id


class TestMemoCompletionHintAugmentResultSummary:
    """augment_result_summary の整形挙動。"""

    def test_hint_result_summary_does_not_change(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """memo が無い / 閾値未満なら augment しても元のまま。"""
        service = _make_hint_service(being_setup)
        being_id = being_setup.being_id_for(1)
        original = "press 成功"
        assert (
            service.augment_result_summary(being_id, "press latch", original)
            == original
        )

    def test_hint_result_summary_hint_append(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """閾値以上の memo があれば result_summary 末尾に [hint] が付く。"""
        being_id = being_setup.being_id_for(1)
        being_setup.memo_store.add_by_being(
            being_id, "金庫室で扉固定スイッチを押す"
        )
        service = _make_hint_service(being_setup, similarity_threshold=0.3)
        augmented = service.augment_result_summary(
            being_id,
            "金庫室で扉固定スイッチを押す",
            "press 成功",
        )
        assert augmented.startswith("press 成功")
        assert "[hint]" in augmented
        assert "memo_done" in augmented


class TestMemoCompletionHintToHintText:
    """MemoCompletionHint.to_hint_text の整形。"""

    def test_hint_memo_id_included(
        self, being_setup: MemoBeingTestSetup
    ) -> None:
        """LLM 向け hint 文に id (短縮形) と類似度が表示される。"""
        being_id = being_setup.being_id_for(1)
        memo_id = being_setup.memo_store.add_by_being(
            being_id, "金庫室で扉固定スイッチを押す"
        )
        memo = being_setup.memo_store.list_uncompleted_by_being(being_id)[0]
        hint = MemoCompletionHint(memo=memo, similarity=0.67)
        text = hint.to_hint_text()
        # Issue #276: id 表示は短縮形 (先頭 6 文字 + …)。元の full UUID は出ない。
        assert memo_id[:6] in text
        assert "0.67" in text
        assert "memo_done" in text


def test_default_similarity_threshold() -> None:
    """既定閾値が [0,1] 範囲内であること。"""
    assert 0.0 <= DEFAULT_SIMILARITY_THRESHOLD <= 1.0
