"""``SpotArrivalEncounterHandler`` の単体テスト (PR4)。

handler の役割: ``EntityEnteredSpotEvent`` を受けて actor 本人の spot
encounter を記録する。observation pipeline 経由 (PR3) との二重記録ではなく、
本人の到着を別経路で取り扱う。
"""

from __future__ import annotations

import logging

import pytest

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)

from ai_rpg_world.application.encounter.handlers.spot_arrival_encounter_handler import (
    SpotArrivalEncounterHandler,
)
from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import (
    SpotGraphId,
)


def _event(
    *,
    entity_int: int = 1,
    spot_int: int = 100,
    from_spot_int: int | None = None,
) -> EntityEnteredSpotEvent:
    return EntityEnteredSpotEvent.create(
        aggregate_id=SpotGraphId.create(1),
        aggregate_type="SpotGraphAggregate",
        entity_id=EntityId.create(entity_int),
        spot_id=SpotId.create(spot_int),
        from_spot_id=None
        if from_spot_int is None
        else SpotId.create(from_spot_int),
    )


@pytest.fixture
def memory() -> InMemoryEncounterMemory:
    return InMemoryEncounterMemory()


@pytest.fixture
def spot_resolver():
    """spot int → str_id (テスト用の固定 mapping)。"""
    table = {100: "forest_clearing", 200: "summit", 300: "shipwreck_beach"}
    return lambda spot_int: table[spot_int]


class TestConstructor:
    def test_memory_が_IEncounterMemory_でなければ_TypeError(
        self, spot_resolver
    ) -> None:
        with pytest.raises(TypeError, match="memory"):
            SpotArrivalEncounterHandler(
                memory="x",  # type: ignore[arg-type]
                current_tick_provider=lambda: 0,
                spot_str_id_resolver=spot_resolver,
            )

    def test_current_tick_provider_が_callable_でなければ_TypeError(
        self, memory, spot_resolver
    ) -> None:
        with pytest.raises(TypeError, match="current_tick_provider"):
            SpotArrivalEncounterHandler(
                memory=memory,
                current_tick_provider=0,  # type: ignore[arg-type]
                spot_str_id_resolver=spot_resolver,
            )

    def test_spot_str_id_resolver_が_callable_でなければ_TypeError(
        self, memory
    ) -> None:
        with pytest.raises(TypeError, match="spot_str_id_resolver"):
            SpotArrivalEncounterHandler(
                memory=memory,
                current_tick_provider=lambda: 0,
                spot_str_id_resolver=None,  # type: ignore[arg-type]
            )


class TestHandle:
    """``EntityEnteredSpotEvent`` を受けて encounter を記録する。"""

    def test_actor_の_spot_encounter_が_記録される(
        self, memory, spot_resolver
    ) -> None:
        handler = SpotArrivalEncounterHandler(
            memory=memory,
            current_tick_provider=lambda: 42,
            spot_str_id_resolver=spot_resolver,
        )
        handler.handle(_event(entity_int=1, spot_int=100))
        record = memory.lookup(
            PlayerId(1), EncounterKey.spot("forest_clearing")
        )
        assert record is not None
        assert record.is_first is True
        assert record.last_seen_tick == 42

    def test_初回_spawn_event_from_spot_None_も_encounter_として記録(
        self, memory, spot_resolver
    ) -> None:
        """from_spot_id=None (初回配置) も同じ経路で記録される。"""
        handler = SpotArrivalEncounterHandler(
            memory=memory,
            current_tick_provider=lambda: 0,
            spot_str_id_resolver=spot_resolver,
        )
        handler.handle(_event(entity_int=1, spot_int=300, from_spot_int=None))
        record = memory.lookup(
            PlayerId(1), EncounterKey.spot("shipwreck_beach")
        )
        assert record is not None
        assert record.is_first is True

    def test_再訪_event_は_count_が_進む(self, memory, spot_resolver) -> None:
        handler = SpotArrivalEncounterHandler(
            memory=memory,
            current_tick_provider=lambda: 10,
            spot_str_id_resolver=spot_resolver,
        )
        handler.handle(_event(entity_int=1, spot_int=200))
        # tick を進めて再訪
        handler._current_tick_provider = lambda: 30  # type: ignore[assignment]
        handler.handle(_event(entity_int=1, spot_int=200))
        record = memory.lookup(PlayerId(1), EncounterKey.spot("summit"))
        assert record is not None
        assert record.count == 2
        assert record.first_seen_tick == 10
        assert record.last_seen_tick == 30

    def test_spot_resolver_が_例外を_投げたら_skip(
        self, memory, caplog
    ) -> None:
        def _bad(spot_int):
            raise KeyError(spot_int)

        handler = SpotArrivalEncounterHandler(
            memory=memory,
            current_tick_provider=lambda: 0,
            spot_str_id_resolver=_bad,
        )
        with caplog.at_level(logging.ERROR):
            handler.handle(_event(entity_int=1, spot_int=100))
        # 例外は外に出ない、record も立たない
        assert memory.get_records_for(PlayerId(1)) == {}

    def test_current_tick_provider_が_例外を_投げたら_skip(
        self, memory, spot_resolver
    ) -> None:
        def _bad_clock() -> int:
            raise RuntimeError("clock unavailable")

        handler = SpotArrivalEncounterHandler(
            memory=memory,
            current_tick_provider=_bad_clock,
            spot_str_id_resolver=spot_resolver,
        )
        handler.handle(_event(entity_int=1, spot_int=100))
        assert memory.get_records_for(PlayerId(1)) == {}

    def test_handle_全体が_例外で_落ちない(
        self, memory, spot_resolver
    ) -> None:
        """memory.observe が破壊された場合でも handle 自体は raise しない
        (silent fail に近いが log は残る、本流の event pipeline を倒さない)。"""

        class _BrokenMemory(InMemoryEncounterMemory):
            def observe(self, *a, **kw):  # type: ignore[override]
                raise RuntimeError("storage failure")

        handler = SpotArrivalEncounterHandler(
            memory=_BrokenMemory(),
            current_tick_provider=lambda: 0,
            spot_str_id_resolver=spot_resolver,
        )
        handler.handle(_event(entity_int=1, spot_int=100))  # raise しないこと
