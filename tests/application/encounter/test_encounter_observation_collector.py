"""EncounterObservationCollector の単体テスト (PR3)。

collector は observation の ``structured`` を読んで encounter 対象を抽出し、
``IEncounterMemory.observe`` を呼ぶ。本テストは抽出ロジックと例外処理の挙動
だけを検証する。observation_pipeline 経由の integration は別ファイル。
"""

from __future__ import annotations

import logging

import pytest

# observation.contracts は llm.services を経由する循環 import を持つので、
# llm 側を先に warm up してから import する (= Phase 9-4c test と同じ順序)。
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
)

from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.encounter.services.encounter_observation_collector import (
    EncounterObservationCollector,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _output(
    *,
    structured: dict | None = None,
    prose: str = "",
    category: str = "social",
) -> ObservationOutput:
    return ObservationOutput(
        prose=prose,
        structured=dict(structured or {}),
        observation_category=category,
        schedules_turn=False,
        breaks_movement=False,
    )


@pytest.fixture
def memory() -> InMemoryEncounterMemory:
    return InMemoryEncounterMemory()


@pytest.fixture
def kai() -> PlayerId:
    return PlayerId(1)


class TestConstructor:
    """型の防衛 (silent failure 防止)。"""

    def test_memory_が_IEncounterMemory_でなければ_TypeError(self) -> None:
        with pytest.raises(TypeError, match="memory"):
            EncounterObservationCollector(
                memory="not a memory",  # type: ignore[arg-type]
                current_tick_provider=lambda: 0,
            )

    def test_current_tick_provider_が_callable_でなければ_TypeError(
        self, memory: InMemoryEncounterMemory
    ) -> None:
        with pytest.raises(TypeError, match="current_tick_provider"):
            EncounterObservationCollector(
                memory=memory,
                current_tick_provider=0,  # type: ignore[arg-type]
            )


class TestEntityEnteredSpot:
    """type=entity_entered_spot の観測から player encounter を抽出する。"""

    def test_actor_を_player_encounter_として_記録する(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 42
        )
        collector.on_observation(
            kai,
            _output(
                structured={
                    "type": "entity_entered_spot",
                    "actor": "ノア",
                    "spot_name": "森の入口",
                }
            ),
        )
        record = memory.lookup(kai, EncounterKey.player("ノア"))
        assert record is not None
        assert record.is_first is True
        assert record.last_seen_tick == 42

    def test_2_度目_の_観測で_count_が_2_に_なる(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 5
        )
        struct = {"type": "entity_entered_spot", "actor": "ノア"}
        collector.on_observation(kai, _output(structured=struct))
        collector.on_observation(
            kai,
            _output(structured=struct),
        )
        record = memory.lookup(kai, EncounterKey.player("ノア"))
        assert record is not None
        assert record.count == 2

    def test_actor_前後の_空白は_strip_される(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(
                structured={"type": "entity_entered_spot", "actor": "  ノア  "}
            ),
        )
        # strip 後の名前で記録される
        assert memory.lookup(kai, EncounterKey.player("ノア")) is not None

    def test_actor_欠落の_観測は_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "entity_entered_spot"}),
        )
        assert memory.get_records_for(kai) == {}

    def test_actor_が_str_でなければ_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(
                structured={"type": "entity_entered_spot", "actor": 42}
            ),
        )
        assert memory.get_records_for(kai) == {}


class TestScenarioEvent:
    """type=scenario_event の観測から event encounter を抽出する。"""

    def test_event_id_を_event_encounter_として_記録する(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 96
        )
        collector.on_observation(
            kai,
            _output(
                structured={
                    "type": "scenario_event",
                    "event_id": "storm_arrives",
                    "message": "嵐が来た",
                },
                category="environment",
            ),
        )
        record = memory.lookup(kai, EncounterKey.event("storm_arrives"))
        assert record is not None
        assert record.first_seen_tick == 96

    def test_event_id_欠落は_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "scenario_event"}),
        )
        assert memory.get_records_for(kai) == {}


class TestUnknownType:
    """PR3 のスコープ外の type は silent skip。"""

    def test_未対応_type_は_何も記録しない(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "something_unrelated"}),
        )
        assert memory.get_records_for(kai) == {}

    def test_structured_が_空でも_落ちない(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(kai, _output(structured={}))
        assert memory.get_records_for(kai) == {}

    def test_type_欠落でも_落ちない(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(structured={"actor": "someone"}),
        )
        assert memory.get_records_for(kai) == {}


class TestCurrentTickFailures:
    """current_tick_provider が異常値を返すケース。"""

    def test_provider_が_例外を_投げたら_log_して_skip(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def _bad_provider() -> int:
            raise RuntimeError("clock unavailable")

        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=_bad_provider
        )
        with caplog.at_level(logging.ERROR):
            collector.on_observation(
                kai,
                _output(
                    structured={"type": "entity_entered_spot", "actor": "ノア"}
                ),
            )
        # encounter は記録されない
        assert memory.get_records_for(kai) == {}

    def test_provider_が_None_を_返したら_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory,
            current_tick_provider=lambda: None,  # type: ignore[arg-type,return-value]
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "entity_entered_spot", "actor": "ノア"}),
        )
        assert memory.get_records_for(kai) == {}

    def test_provider_が_負の_int_を_返したら_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: -1
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "entity_entered_spot", "actor": "ノア"}),
        )
        assert memory.get_records_for(kai) == {}


class TestExceptionInMemoryObserve:
    """memory.observe が例外を投げても本流を止めない (= silent skip + log)。"""

    def test_memory_observe_が_例外を_投げても_例外を_伝播させない(
        self,
        kai: PlayerId,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        class _BrokenMemory(InMemoryEncounterMemory):
            def observe(self, *args, **kwargs):  # type: ignore[override]
                raise RuntimeError("storage failure")

        collector = EncounterObservationCollector(
            memory=_BrokenMemory(), current_tick_provider=lambda: 0
        )
        with caplog.at_level(logging.ERROR):
            # 例外が外に出ないことを確認
            collector.on_observation(
                kai,
                _output(
                    structured={"type": "entity_entered_spot", "actor": "ノア"}
                ),
            )
