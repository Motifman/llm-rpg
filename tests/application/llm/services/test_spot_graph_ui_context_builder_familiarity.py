"""``SpotGraphUiContextBuilder`` の familiarity 注記テスト (PR4)。

PR4 で追加された機能:

- 「現在地: 〇〇」line に ``(初めて訪れた)`` を追加
- 「同じ場所にいるプレイヤー」の名前に ``(初めて会った)`` を追加
- encounter_memory が未注入の場合は完全に既存挙動 (= 注記なし)

dto 構築は重いので unit test は internal helper を直接呼んで挙動を担保する。
end-to-end の経路 (= 実 PlayerCurrentStateDto → ui_context_builder → 注記) は
``tests/integration/test_encounter_memory_prompt_integration.py`` 側で担保する。
"""

from __future__ import annotations

import pytest

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SPOT_NAMES = {100: "forest_clearing", 200: "summit"}


def _make_builder(memory: InMemoryEncounterMemory, tick: int = 0):
    return SpotGraphUiContextBuilder(
        encounter_memory=memory,
        current_tick_provider=lambda: tick,
        spot_str_id_resolver=lambda i: _SPOT_NAMES[i],
    )


class TestSpotFamiliarityAnnotation:
    """``_spot_familiarity_annotation`` の挙動。"""

    def test_初訪問_spot_は_初めて訪れた_注記(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        builder = _make_builder(memory)
        annotation = builder._spot_familiarity_annotation(PlayerId(1), 100)
        assert annotation == "(初めて訪れた)"

    def test_再訪_spot_は_PR4_範囲では_None(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 5)
        builder = _make_builder(memory)
        assert builder._spot_familiarity_annotation(PlayerId(1), 100) is None

    def test_未_observe_な_spot_は_None(self) -> None:
        memory = InMemoryEncounterMemory()
        builder = _make_builder(memory)
        assert builder._spot_familiarity_annotation(PlayerId(1), 100) is None

    def test_resolver_が_例外を_投げても_None_に_縮退(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        builder = SpotGraphUiContextBuilder(
            encounter_memory=memory,
            current_tick_provider=lambda: 0,
            spot_str_id_resolver=lambda i: (_ for _ in ()).throw(KeyError(i)),
        )
        assert builder._spot_familiarity_annotation(PlayerId(1), 100) is None


class TestPlayerFamiliarityAnnotation:
    """``_player_familiarity_annotation`` の挙動。"""

    def test_初対面_player_は_初めて会った_注記(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.player("ノア"), 0)
        builder = _make_builder(memory)
        assert (
            builder._player_familiarity_annotation(PlayerId(1), "ノア")
            == "(初めて会った)"
        )

    def test_再会_player_は_PR4_範囲では_None(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.player("ノア"), 0)
        memory.observe(PlayerId(1), EncounterKey.player("ノア"), 5)
        builder = _make_builder(memory)
        assert (
            builder._player_familiarity_annotation(PlayerId(1), "ノア") is None
        )

    def test_未_observe_な_player_は_None(self) -> None:
        memory = InMemoryEncounterMemory()
        builder = _make_builder(memory)
        assert (
            builder._player_familiarity_annotation(PlayerId(1), "ノア") is None
        )

    def test_display_name_が_空文字なら_None(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.player("ノア"), 0)
        builder = _make_builder(memory)
        assert builder._player_familiarity_annotation(PlayerId(1), "") is None

    def test_viewer_id_が_None_なら_None(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.player("ノア"), 0)
        builder = _make_builder(memory)
        assert builder._player_familiarity_annotation(None, "ノア") is None


class TestEncounterEnabledGuard:
    """3 要素 (memory / tick_provider / resolver) のいずれかが欠ければ off。"""

    def test_3_要素_全部_揃って_initial_enabled(self) -> None:
        memory = InMemoryEncounterMemory()
        builder = _make_builder(memory)
        assert builder._encounter_enabled() is True

    def test_memory_のみで_disabled(self) -> None:
        memory = InMemoryEncounterMemory()
        builder = SpotGraphUiContextBuilder(encounter_memory=memory)
        assert builder._encounter_enabled() is False

    def test_完全未注入で_disabled(self) -> None:
        builder = SpotGraphUiContextBuilder()
        assert builder._encounter_enabled() is False

    def test_disabled_時_player_注記は_出ない(self) -> None:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.player("ノア"), 0)
        builder = SpotGraphUiContextBuilder(encounter_memory=memory)
        # tick / resolver が無いので encounter_enabled=False
        assert (
            builder._player_familiarity_annotation(PlayerId(1), "ノア") is None
        )


class TestConstructorTypeChecks:
    def test_encounter_memory_が_IEncounterMemory_でなければ_TypeError(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="encounter_memory"):
            SpotGraphUiContextBuilder(
                encounter_memory="x"  # type: ignore[arg-type]
            )

    def test_current_tick_provider_が_callable_でなければ_TypeError(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="current_tick_provider"):
            SpotGraphUiContextBuilder(
                current_tick_provider=0  # type: ignore[arg-type]
            )

    def test_spot_str_id_resolver_が_callable_でなければ_TypeError(
        self,
    ) -> None:
        with pytest.raises(TypeError, match="spot_str_id_resolver"):
            SpotGraphUiContextBuilder(
                spot_str_id_resolver=0  # type: ignore[arg-type]
            )


class TestAnnotateCurrentSpotText:
    """``_annotate_current_spot_familiarity`` (= 文字列 inject) のテスト。"""

    @pytest.fixture
    def builder(self) -> SpotGraphUiContextBuilder:
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        return _make_builder(memory)

    def test_初訪問の_spot_行を_書き換える(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        # snap stub: SimpleNamespace で必要 field だけ
        from types import SimpleNamespace

        snap = SimpleNamespace(
            current_spot_id=100, current_spot_name="森の広場"
        )
        original = "現在地: 森の広場\n  description"
        out = builder._annotate_current_spot_familiarity(
            original, snap, PlayerId(1)
        )
        assert "現在地: 森の広場 (初めて訪れた)\n  description" == out

    def test_注記なしの_spot_行は_書き換えない(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=200, current_spot_name="山頂")
        original = "現在地: 山頂\n  description"
        # spot 200 (summit) は未 observe なので注記なし
        out = builder._annotate_current_spot_familiarity(
            original, snap, PlayerId(1)
        )
        assert out == original

    def test_spot_id_が_None_なら_書き換えない(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=None, current_spot_name="不明")
        original = "現在地: 不明"
        out = builder._annotate_current_spot_familiarity(
            original, snap, PlayerId(1)
        )
        assert out == original

    def test_viewer_None_なら_書き換えない(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=100, current_spot_name="森の広場")
        original = "現在地: 森の広場"
        out = builder._annotate_current_spot_familiarity(original, snap, None)
        assert out == original

    def test_spot_名が_description_に_部分文字列として_含まれても_誤置換しない(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        """``str.replace`` で部分一致させると description に紛れた名前まで
        書き換えてしまう。完全一致の行のみ置換する仕様を担保する。"""
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=100, current_spot_name="森の広場")
        # description にも「森の広場」が部分一致で混入する形を想定
        original = (
            "現在地: 森の広場\n"
            "  ここは「森の広場」と呼ばれる場所だ。"
        )
        out = builder._annotate_current_spot_familiarity(
            original, snap, PlayerId(1)
        )
        # 1 行目だけが書き換わる、2 行目の「森の広場」は触られない
        assert out.splitlines()[0] == "現在地: 森の広場 (初めて訪れた)"
        assert out.splitlines()[1] == "  ここは「森の広場」と呼ばれる場所だ。"
