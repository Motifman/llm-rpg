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

    def test_memory_ien_count_er_memory_raises_type_error(self) -> None:
        """memory が IEncounterMemory でなければ TypeError。"""
        with pytest.raises(TypeError, match="memory"):
            EncounterObservationCollector(
                memory="not a memory",  # type: ignore[arg-type]
                current_tick_provider=lambda: 0,
            )

    def test_current_tick_provider_callable_raises_type_error(
        self, memory: InMemoryEncounterMemory
    ) -> None:
        """current tick provider が callable でなければ TypeError。"""
        with pytest.raises(TypeError, match="current_tick_provider"):
            EncounterObservationCollector(
                memory=memory,
                current_tick_provider=0,  # type: ignore[arg-type]
            )


class TestEntityEnteredSpot:
    """type=entity_entered_spot の観測から player encounter を抽出する。"""

    def test_records_actor_player_encounter(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """actor を player encounter として 記録する。"""
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

    def test_two_observation_count_two(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """2 度目の観測で count が 2 になる。"""
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

    def test_actor_around_blank_strip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """actor 前後の 空白は strip される。"""
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

    def test_actor_missing_observation_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """actor 欠落の 観測は skip。"""
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "entity_entered_spot"}),
        )
        assert memory.get_records_for(kai) == {}

    def test_actor_str_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """actor が str でなければ skip。"""
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

    def test_records_event_id_event_encounter(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """event id を event encounter として 記録する。"""
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

    def test_event_id_missing_skip(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """event id 欠落は skip。"""
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

    def test_records_nothing_for_unsupported_type(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """未対応 type は何も記録しない。"""
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "something_unrelated"}),
        )
        assert memory.get_records_for(kai) == {}

    def test_structured_empty_does_not_crash(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """structured が空でも落ちない。"""
        collector = EncounterObservationCollector(
            memory=memory, current_tick_provider=lambda: 0
        )
        collector.on_observation(kai, _output(structured={}))
        assert memory.get_records_for(kai) == {}

    def test_type_missing_does_not_crash(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """type 欠落でも 落ちない。"""
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

    def test_provider_log_skip_raises_exception(
        self,
        memory: InMemoryEncounterMemory,
        kai: PlayerId,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """provider が例外を投げたら log して skip。"""
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

    def test_returns_skip_provider_none_when(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """provider が None を返したら skip。"""
        collector = EncounterObservationCollector(
            memory=memory,
            current_tick_provider=lambda: None,  # type: ignore[arg-type,return-value]
        )
        collector.on_observation(
            kai,
            _output(structured={"type": "entity_entered_spot", "actor": "ノア"}),
        )
        assert memory.get_records_for(kai) == {}

    def test_returns_skip_provider_negative_int_when(
        self, memory: InMemoryEncounterMemory, kai: PlayerId
    ) -> None:
        """provider が負の int を返したら skip。"""
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

    def test_memory_observe_raises_exception(
        self,
        kai: PlayerId,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """memoryobserve が例外を投げても例外を伝播させない。"""
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
