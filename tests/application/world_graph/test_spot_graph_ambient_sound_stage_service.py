"""SpotGraphAmbientSoundStageService の単体テスト。"""

from __future__ import annotations

import random
from typing import List
from unittest.mock import MagicMock

from ai_rpg_world.application.world_graph.spot_graph_ambient_sound_stage_service import (
    SpotGraphAmbientSoundStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    AmbientSoundEmittedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_atlas import (
    AmbientSoundAtlas,
    AmbientSoundConfig,
    AmbientSoundThrottleConfig,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_def import (
    AmbientSoundDef,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_filter import (
    AmbientSoundFilter,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


def _build_graph(spots: dict[int, dict], placements: dict[int, int]) -> SpotGraphAggregate:
    """spots: {spot_id: {is_outdoor, ambient_tags}}"""
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    for sid, attrs in spots.items():
        graph.add_spot(
            SpotNode(
                spot_id=SpotId.create(sid),
                name=f"spot_{sid}",
                description="",
                category=SpotCategoryEnum.TOWN,
                parent_id=None,
                is_outdoor=attrs.get("is_outdoor", False),
                ambient_tags=frozenset(attrs.get("ambient_tags", ())),
            )
        )
    for eid, sid in placements.items():
        graph.place_entity(EntityId.create(eid), SpotId.create(sid))
    graph.clear_events()
    return graph


def _make_status_repo(player_ids: list[int]):
    statuses = []
    for pid in player_ids:
        s = MagicMock()
        s.player_id = PlayerId(pid)
        statuses.append(s)
    repo = MagicMock()
    repo.find_all.return_value = statuses
    return repo


def _config(*, enabled=True, interval=1, defs=()) -> AmbientSoundConfig:
    return AmbientSoundConfig(
        enabled=enabled,
        update_interval_ticks=interval,
        throttle=AmbientSoundThrottleConfig(),
        atlas=AmbientSoundAtlas(defs=tuple(defs)),
    )


def _drip_def(probability: float = 1.0, **filter_kwargs) -> AmbientSoundDef:
    return AmbientSoundDef(
        id="drip",
        tags=frozenset({"wet"}),
        prose="水滴の音がする",
        probability_per_tick=probability,
        sound_strength=0.3,
        filters=AmbientSoundFilter(**filter_kwargs),
    )


class _Recorder:
    def __init__(self):
        self.events: List[AmbientSoundEmittedEvent] = []

    def emit(self, ev):
        self.events.append(ev)


def _make_service(*, graph, config, **kwargs) -> SpotGraphAmbientSoundStageService:
    repo = MagicMock()
    repo.find_graph.return_value = graph
    rec = _Recorder()
    return SpotGraphAmbientSoundStageService(
        config=config,
        spot_graph_repository=repo,
        spot_graph_id=SpotGraphId.create(1),
        player_status_repository=_make_status_repo(kwargs.get("known_players", [1])),
        emit=rec.emit,
        time_of_day_provider=kwargs.get("time_of_day_provider"),
        weather_state_provider=kwargs.get("weather_state_provider"),
        rng=kwargs.get("rng", random.Random(42)),
    ), rec


class TestStageGuards:
    def test_disabled_skips(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        service, rec = _make_service(
            graph=graph,
            config=_config(enabled=False, defs=(_drip_def(),)),
        )
        service.run(WorldTick(0))
        assert rec.events == []

    def test_empty_atlas_skips(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        service, rec = _make_service(graph=graph, config=_config(defs=()))
        service.run(WorldTick(0))
        assert rec.events == []

    def test_interval_throttles(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        service, rec = _make_service(
            graph=graph,
            config=_config(interval=3, defs=(_drip_def(),)),
        )
        service.run(WorldTick(1))
        service.run(WorldTick(2))
        assert rec.events == []
        service.run(WorldTick(3))
        assert len(rec.events) == 1

    def test_no_players_skips(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {})
        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(_drip_def(),)),
            known_players=[],
        )
        service.run(WorldTick(0))
        assert rec.events == []

    def test_spot_without_tags_skipped(self):
        graph = _build_graph({1: {}, 2: {"ambient_tags": ("wet",)}}, {1: 1, 2: 2})
        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(_drip_def(),)),
            known_players=[1, 2],
        )
        service.run(WorldTick(0))
        assert len(rec.events) == 1
        assert rec.events[0].source_spot_id == SpotId.create(2)


class TestStageFilters:
    def test_phase_filter_blocks(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        sound = _drip_def(phases=frozenset({"night"}))

        def tod_provider():
            return TimeOfDay(0.0, "day", "昼", 1.0, False)

        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(sound,)),
            time_of_day_provider=tod_provider,
        )
        service.run(WorldTick(0))
        assert rec.events == []

    def test_phase_filter_allows(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        sound = _drip_def(phases=frozenset({"night"}))

        def tod_provider():
            return TimeOfDay(0.9, "night", "夜", 0.1, True)

        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(sound,)),
            time_of_day_provider=tod_provider,
        )
        service.run(WorldTick(0))
        assert len(rec.events) == 1

    def test_weather_filter_blocks(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        sound = _drip_def(weather_types=frozenset({"RAIN"}))

        def w_provider():
            return WeatherState(WeatherTypeEnum.CLEAR, 1.0)

        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(sound,)),
            weather_state_provider=w_provider,
        )
        service.run(WorldTick(0))
        assert rec.events == []

    def test_indoor_only_blocks_outdoor(self):
        graph = _build_graph(
            {1: {"ambient_tags": ("wet",), "is_outdoor": True}},
            {1: 1},
        )
        sound = _drip_def(indoor_only=True)
        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(sound,)),
        )
        service.run(WorldTick(0))
        assert rec.events == []


class TestStageRolling:
    def test_zero_probability_never_fires(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(_drip_def(probability=0.0),)),
            rng=random.Random(0),
        )
        for t in range(20):
            service.run(WorldTick(t))
        assert rec.events == []

    def test_emits_event_with_correct_payload(self):
        graph = _build_graph({1: {"ambient_tags": ("wet",)}}, {1: 1})
        service, rec = _make_service(
            graph=graph,
            config=_config(defs=(_drip_def(probability=1.0),)),
        )
        service.run(WorldTick(0))
        assert len(rec.events) == 1
        ev = rec.events[0]
        assert ev.ambient_sound_id == "drip"
        assert ev.prose == "水滴の音がする"
        assert ev.sound_strength == 0.3
        assert ev.source_spot_id == SpotId.create(1)
