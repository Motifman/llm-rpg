"""``SpotGraphUiContextBuilder`` の familiarity 注記テスト (PR4)。

PR4 で追加された機能:

- 「現在地: 〇〇」line に ``(初めて訪れた)`` を追加
- 「同じ場所にいるプレイヤー」の名前に ``(初めて会った)`` を追加 (Being の知り合いの記録から)
- encounter_memory / acquaintances が未注入の場合は注記なし

dto 構築は重いので unit test は internal helper を直接呼んで挙動を担保する。
end-to-end の経路 (= 実 PlayerCurrentStateDto → ui_context_builder → 注記) は
``tests/integration/test_encounter_memory_prompt_integration.py`` 側で担保する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_expectation_repository import (
    InMemoryExpectationRepository,
)

_SPOT_NAMES = {100: "forest_clearing", 200: "summit"}


def _acquaintances() -> PlayerAcquaintances:
    return PlayerAcquaintances(
        store=InMemoryAcquaintanceRepository(),
        being_id_of=lambda pid: BeingId(f"being_p{pid.value}"),
        turn_reader=InMemoryExpectationRepository(),
        environment_name="森",
        names_by_player_id={1: "エイダ", 2: "カイ", 3: "ノア"},
    )


def _make_builder(memory: InMemoryEncounterMemory, tick: int = 0):
    return SpotGraphUiContextBuilder(
        encounter_memory=memory,
        current_tick_provider=lambda: tick,
        spot_str_id_resolver=lambda i: _SPOT_NAMES[i],
    )


class TestSpotFamiliarityAnnotation:
    """``_spot_familiarity_annotation`` の挙動。"""

    def test_first_visit_spot_gets_first_visit_note(self) -> None:
        """初訪問 spot は初めて訪れた注記。"""
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        builder = _make_builder(memory)
        annotation = builder._spot_familiarity_annotation(PlayerId(1), 100)
        assert annotation == "(初めて訪れた)"

    def test_spot_pr4_none(self) -> None:
        """再訪 spot は PR4 範囲では None。"""
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 5)
        builder = _make_builder(memory)
        assert builder._spot_familiarity_annotation(PlayerId(1), 100) is None

    def test_observe_spot_none(self) -> None:
        """未 observe な spot は None。"""
        memory = InMemoryEncounterMemory()
        builder = _make_builder(memory)
        assert builder._spot_familiarity_annotation(PlayerId(1), 100) is None

    def test_resolver_exception_falls_back_to_none(self) -> None:
        """resolver が例外を投げても None に縮退。"""
        memory = InMemoryEncounterMemory()
        memory.observe(PlayerId(1), EncounterKey.spot("forest_clearing"), 0)
        builder = SpotGraphUiContextBuilder(
            encounter_memory=memory,
            current_tick_provider=lambda: 0,
            spot_str_id_resolver=lambda i: (_ for _ in ()).throw(KeyError(i)),
        )
        assert builder._spot_familiarity_annotation(PlayerId(1), 100) is None


class TestPlayerFamiliarityAnnotation:
    """``_player_familiarity_annotation`` が、見ている側の Being の知り合いの記録から「初めて会った」を決めることを保証する。"""

    def test_person_met_once_gets_first_meeting_note(self) -> None:
        """一度だけ会った相手には (初めて会った) を付ける。"""
        acquaintances = _acquaintances()
        acquaintances.record_meeting(PlayerId(1), "ノア")
        builder = SpotGraphUiContextBuilder(acquaintances=acquaintances)
        assert (
            builder._player_familiarity_annotation(PlayerId(1), "ノア")
            == "(初めて会った)"
        )

    def test_person_met_twice_gets_no_note(self) -> None:
        """二度以上会った相手には注記を付けない。"""
        acquaintances = _acquaintances()
        acquaintances.record_meeting(PlayerId(1), "ノア")
        acquaintances.record_meeting(PlayerId(1), "ノア")
        builder = SpotGraphUiContextBuilder(acquaintances=acquaintances)
        assert builder._player_familiarity_annotation(PlayerId(1), "ノア") is None

    def test_person_never_met_gets_no_note(self) -> None:
        """会った記録の無い相手には注記を付けない。"""
        builder = SpotGraphUiContextBuilder(acquaintances=_acquaintances())
        assert builder._player_familiarity_annotation(PlayerId(1), "ノア") is None

    def test_meeting_of_another_viewer_does_not_count(self) -> None:
        """別のプレイヤーが会った記録は、見ている側の注記に使わない。"""
        acquaintances = _acquaintances()
        acquaintances.record_meeting(PlayerId(2), "ノア")
        builder = SpotGraphUiContextBuilder(acquaintances=acquaintances)
        assert builder._player_familiarity_annotation(PlayerId(1), "ノア") is None

    def test_blank_name_or_missing_viewer_gets_no_note(self) -> None:
        """表示名が空のときと、見ている側が分からないときは注記を付けない。"""
        acquaintances = _acquaintances()
        acquaintances.record_meeting(PlayerId(1), "ノア")
        builder = SpotGraphUiContextBuilder(acquaintances=acquaintances)
        assert builder._player_familiarity_annotation(PlayerId(1), "") is None
        assert builder._player_familiarity_annotation(None, "ノア") is None

    def test_environment_encounter_alone_gives_no_note(self) -> None:
        """知り合いの記録を渡さなければ、環境の encounter が揃っていても人に注記を付けない。"""
        builder = _make_builder(InMemoryEncounterMemory())
        assert builder._player_familiarity_annotation(PlayerId(1), "ノア") is None


class TestEncounterEnabledGuard:
    """3 要素 (memory / tick_provider / resolver) のいずれかが欠ければ off。"""

    def test_three_element_all_initial_enabled(self) -> None:
        """3 要素 全部 揃って initial enabled。"""
        memory = InMemoryEncounterMemory()
        builder = _make_builder(memory)
        assert builder._encounter_enabled() is True

    def test_memory_disabled(self) -> None:
        """memory のみで disabled。"""
        memory = InMemoryEncounterMemory()
        builder = SpotGraphUiContextBuilder(encounter_memory=memory)
        assert builder._encounter_enabled() is False

    def test_all_uninjected_disabled(self) -> None:
        """完全未注入で disabled。"""
        builder = SpotGraphUiContextBuilder()
        assert builder._encounter_enabled() is False


class TestConstructorTypeChecks:
    def test_en_count_er_memory_ien_count_er_memory_raises_type_error(
        self,
    ) -> None:
        """encounter memory が IEncounterMemory でなければ TypeError。"""
        with pytest.raises(TypeError, match="encounter_memory"):
            SpotGraphUiContextBuilder(
                encounter_memory="x"  # type: ignore[arg-type]
            )

    def test_current_tick_provider_callable_raises_type_error(
        self,
    ) -> None:
        """current tick provider が callable でなければ TypeError。"""
        with pytest.raises(TypeError, match="current_tick_provider"):
            SpotGraphUiContextBuilder(
                current_tick_provider=0  # type: ignore[arg-type]
            )

    def test_spot_str_id_resolver_callable_raises_type_error(
        self,
    ) -> None:
        """spot str id resolver が callable でなければ TypeError。"""
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

    def test_spot_line_2(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        """初訪問の spot 行を 書き換える。"""
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

    def test_spot_line(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        """注記なしの spot 行は 書き換えない。"""
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=200, current_spot_name="山頂")
        original = "現在地: 山頂\n  description"
        # spot 200 (summit) は未 observe なので注記なし
        out = builder._annotate_current_spot_familiarity(
            original, snap, PlayerId(1)
        )
        assert out == original

    def test_spot_id_none(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        """spot id が None なら 書き換えない。"""
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=None, current_spot_name="不明")
        original = "現在地: 不明"
        out = builder._annotate_current_spot_familiarity(
            original, snap, PlayerId(1)
        )
        assert out == original

    def test_viewer_none(
        self, builder: SpotGraphUiContextBuilder
    ) -> None:
        """viewer None なら 書き換えない。"""
        from types import SimpleNamespace

        snap = SimpleNamespace(current_spot_id=100, current_spot_name="森の広場")
        original = "現在地: 森の広場"
        out = builder._annotate_current_spot_familiarity(original, snap, None)
        assert out == original

    def test_spot_description_string(
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
