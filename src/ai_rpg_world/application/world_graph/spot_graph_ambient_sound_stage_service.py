"""環境音レイヤーのステージサービス。

シミュレーションループから tick ごとに呼ばれ、
- update_interval_ticks ごとにロール
- プレイヤーが在席するスポットのみ対象（無人空間で音を発生させても誰も聞かない）
- 各スポットの ambient_tags と atlas の交差した def 候補に対して
  フェーズ・天候・屋内屋外フィルタを適用
- probability_per_tick で抽選し、当選したら AmbientSoundEmittedEvent を emit

per-player throttle（同一プレイヤーへの過剰配信抑止）は本ステージではなく
recipient strategy 側の責務とする（PR-G）。
"""

from __future__ import annotations

import random
from typing import Callable, Optional, Set

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    AmbientSoundEmittedEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.ambient_sound_atlas import (
    AmbientSoundConfig,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


EventEmitter = Callable[[AmbientSoundEmittedEvent], None]


class SpotGraphAmbientSoundStageService:
    """環境音発火を司る tick ステージサービス。"""

    def __init__(
        self,
        *,
        config: AmbientSoundConfig,
        spot_graph_repository: ISpotGraphRepository,
        spot_graph_id: SpotGraphId,
        player_status_repository: PlayerStatusRepository,
        emit: EventEmitter,
        time_of_day_provider: Optional[Callable[[], Optional[TimeOfDay]]] = None,
        weather_state_provider: Optional[Callable[[], Optional[WeatherState]]] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._config = config
        self._spot_graph_repository = spot_graph_repository
        self._spot_graph_id = spot_graph_id
        self._player_status_repository = player_status_repository
        self._emit = emit
        self._time_of_day_provider = time_of_day_provider
        self._weather_state_provider = weather_state_provider
        self._rng = rng or random.Random()

    def run(self, current_tick: WorldTick) -> None:
        if not self._config.enabled:
            return
        if self._config.atlas.is_empty():
            return
        if current_tick.value % self._config.update_interval_ticks != 0:
            return

        graph = self._spot_graph_repository.find_graph()
        spots_with_players = self._spots_with_players(graph)
        if not spots_with_players:
            return

        time_of_day = (
            self._time_of_day_provider() if self._time_of_day_provider else None
        )
        weather = (
            self._weather_state_provider() if self._weather_state_provider else None
        )
        weather_type_value = (
            weather.weather_type.value if weather is not None else None
        )
        phase_name = time_of_day.phase_name if time_of_day is not None else None

        for spot_id in spots_with_players:
            if not graph.contains_spot(spot_id):
                continue
            spot = graph.get_spot(spot_id)
            tags = spot.ambient_tags
            if not tags:
                continue
            for sound_def in self._config.atlas.candidates_for_tags(tags):
                if not sound_def.filters.matches_phase(phase_name):
                    continue
                if not sound_def.filters.matches_weather(weather_type_value):
                    continue
                if not sound_def.filters.matches_outdoor(spot.is_outdoor):
                    continue
                if self._rng.random() >= sound_def.probability_per_tick:
                    continue
                self._emit(
                    AmbientSoundEmittedEvent.create(
                        aggregate_id=self._spot_graph_id,
                        aggregate_type="SpotGraph",
                        source_spot_id=spot_id,
                        ambient_sound_id=sound_def.id,
                        prose=sound_def.prose,
                        sound_strength=sound_def.sound_strength,
                    )
                )

    def _spots_with_players(self, graph) -> Set[SpotId]:
        """プレイヤーが少なくとも1人いるスポットの集合を返す。"""
        known_player_ids = {
            s.player_id.value for s in self._player_status_repository.find_all()
        }
        result: Set[SpotId] = set()
        for entity_id, spot_id in graph.entity_spot_mapping().items():
            if entity_id.value in known_player_ids:
                result.add(spot_id)
        return result
