"""MemoCompletionHintService の挙動テスト (Issue #188 Phase 1c)。

Phase 3 Step 3a-3: Resolver+WorldId 必須化に伴い、Being を provision して
being_id 経由で memo を追加・参照する構成に書換。
"""

import pytest

from ai_rpg_world.application.llm.services.in_memory_memo_store import InMemoryMemoStore
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    DEFAULT_SIMILARITY_THRESHOLD,
    MemoCompletionHint,
    MemoCompletionHintService,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from tests.application.llm._memo_being_test_helpers import (
    MemoBeingTestSetup,
    make_memo_being_setup,
)


@pytest.fixture
def player_id() -> PlayerId:
    return PlayerId(1)


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
    """Resolver/WorldId を注入した HintService を組み立てる helper。"""
    return MemoCompletionHintService(
        memo_store=being_setup.memo_store,
        similarity_threshold=similarity_threshold,
        being_attachment_resolver=being_setup.resolver,
        default_world_id=being_setup.world_id,
    )


class TestMemoCompletionHintServiceConstruction:
    """MemoCompletionHintService コンストラクタの引数バリデーション挙動。"""

    def test_memo_store_が_MemoRepository_でなければ_TypeError_を投げる(self) -> None:
        """memo_store が MemoRepository 実装でない場合は TypeError。"""
        with pytest.raises(TypeError, match="memo_store"):
            MemoCompletionHintService(memo_store="not-a-store")  # type: ignore[arg-type]

    def test_threshold_が_範囲外なら_ValueError_を投げる(self) -> None:
        """similarity_threshold は [0.0, 1.0] 範囲外なら ValueError。"""
        store = InMemoryMemoStore()
        with pytest.raises(ValueError):
            MemoCompletionHintService(memo_store=store, similarity_threshold=1.5)
        with pytest.raises(ValueError):
            MemoCompletionHintService(memo_store=store, similarity_threshold=-0.1)


class TestMemoCompletionHintDetect:
    """detect の hint 検出挙動。"""

    def test_未完了_memo_が_無ければ_None_を返す(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
    ) -> None:
        """memo_store が空なら hint なし (None)。"""
        service = _make_hint_service(being_setup)
        assert service.detect(player_id, "act", "res") is None

    def test_類似度が閾値未満なら_None_を返す(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
    ) -> None:
        """全 memo が閾値未満なら hint なし。"""
        being_setup.memo_store.add_by_being(
            being_setup.being_id_for(1), "金庫室で扉固定スイッチを押す"
        )
        service = _make_hint_service(being_setup)
        # 全く無関係な行動
        result = service.detect(
            player_id,
            action_summary="speak to カイト",
            result_summary="話しかけた",
        )
        assert result is None

    def test_類似度が閾値以上なら_hint_を返す(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
    ) -> None:
        """memo content と action/result が十分に類似していれば hint。"""
        memo_id = being_setup.memo_store.add_by_being(
            being_setup.being_id_for(1), "金庫室で扉固定スイッチを押す"
        )
        service = _make_hint_service(being_setup, similarity_threshold=0.3)
        result = service.detect(
            player_id,
            action_summary="金庫室で扉固定スイッチを押す",
            result_summary="press 成功",
        )
        assert result is not None
        assert result.memo.id == memo_id
        assert result.similarity >= 0.3

    def test_複数_memo_の中から最も類似度の高いものを選ぶ(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
    ) -> None:
        """複数候補があれば最高 ratio の memo を返す。"""
        store = being_setup.memo_store
        being_id = being_setup.being_id_for(1)
        store.add_by_being(being_id, "リンと合流する")
        target_id = store.add_by_being(being_id, "金庫室で扉固定スイッチを押す")
        service = _make_hint_service(being_setup, similarity_threshold=0.3)
        result = service.detect(
            player_id,
            action_summary="金庫室で扉固定スイッチを押した",
            result_summary="latch engaged",
        )
        assert result is not None
        assert result.memo.id == target_id


class TestMemoCompletionHintAugmentResultSummary:
    """augment_result_summary の整形挙動。"""

    def test_hint_なしなら_result_summary_を変更しない(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
    ) -> None:
        """memo が無い / 閾値未満なら augment しても元のまま。"""
        service = _make_hint_service(being_setup)
        original = "press 成功"
        assert (
            service.augment_result_summary(player_id, "press latch", original)
            == original
        )

    def test_hint_ありなら_result_summary_に_hint_を_append_する(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
    ) -> None:
        """閾値以上の memo があれば result_summary 末尾に [hint] が付く。"""
        being_setup.memo_store.add_by_being(
            being_setup.being_id_for(1), "金庫室で扉固定スイッチを押す"
        )
        service = _make_hint_service(being_setup, similarity_threshold=0.3)
        augmented = service.augment_result_summary(
            player_id,
            "金庫室で扉固定スイッチを押す",
            "press 成功",
        )
        assert augmented.startswith("press 成功")
        assert "[hint]" in augmented
        assert "memo_done" in augmented


class TestMemoCompletionHintToHintText:
    """MemoCompletionHint.to_hint_text の整形。"""

    def test_hint_文に_memo_id_と_類似度が含まれる(
        self, player_id: PlayerId, being_setup: MemoBeingTestSetup
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


def test_DEFAULT_SIMILARITY_THRESHOLD_は_範囲内() -> None:
    """既定閾値が [0,1] 範囲内であること。"""
    assert 0.0 <= DEFAULT_SIMILARITY_THRESHOLD <= 1.0
