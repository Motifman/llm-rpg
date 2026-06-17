"""``SpotArrivalEncounterHandler``: actor 本人の spot encounter を記録する handler。

PR3 では observation pipeline 経由で **他 player の到着**を受け手の encounter
として記録するようになった。本 PR (PR4) では **actor 本人の到着** を別経路で
encounter として記録する。

両者を分けて扱う理由:

- observation pipeline は「観測する側」(= 受け手) に届く仕組みであり、actor
  本人は EntityEnteredSpotEvent の recipient filter で除外される
- 一方 EntityEnteredSpotEvent 自体は actor / 場所 / 出発地の情報を持つので、
  side handler で直接受ければ actor 本人の spot encounter (= 初訪問 / 再訪)
  を自然に記録できる
- 初回 spawn 時の placement も同じ EntityEnteredSpotEvent (from_spot_id=None)
  を emit するため、本 handler 経由で「初めての世界との接点」も漏れなく
  捕捉できる
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ai_rpg_world.application.encounter.contracts.interfaces import (
    IEncounterMemory,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
)


_logger = logging.getLogger(__name__)


# spot int_id → str_id を逆引きする関数の型。``ScenarioIdMapper.get_str("spot", int)``
# を bind して渡す想定。
SpotStrIdResolver = Callable[[int], str]


class SpotArrivalEncounterHandler(EventHandler[EntityEnteredSpotEvent]):
    """actor が spot に到着 (初回 spawn 含む) するたびに encounter を記録する。

    本 handler は PipelineEventPublisher の side handler として register される。
    observation pipeline とは独立に走るため、recipient filter の影響を受けず
    **actor 本人**の familiarity 信号を残せる。

    EntityId は EntityId.value == PlayerId.value という前提に乗る (= 既存
    spot graph runtime と同じ map 方式)。actor が NPC / monster の場合は
    handle 内で player 判定して skip する余地もあるが、PR4 のスコープでは
    そのまま記録する (= scenario が player を作る場合は player 扱いされる)。
    """

    def __init__(
        self,
        memory: IEncounterMemory,
        current_tick_provider: Callable[[], int],
        spot_str_id_resolver: SpotStrIdResolver,
    ) -> None:
        if not isinstance(memory, IEncounterMemory):
            raise TypeError(
                f"memory must be IEncounterMemory (got {type(memory)!r})"
            )
        if not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable")
        if not callable(spot_str_id_resolver):
            raise TypeError("spot_str_id_resolver must be callable")
        self._memory = memory
        self._current_tick_provider = current_tick_provider
        self._spot_str_id_resolver = spot_str_id_resolver

    def handle(self, event: EntityEnteredSpotEvent) -> None:
        try:
            self._handle_impl(event)
        except Exception:
            _logger.exception(
                "SpotArrivalEncounterHandler.handle failed (event=%r)", event
            )

    def _handle_impl(self, event: EntityEnteredSpotEvent) -> None:
        entity_int = int(event.entity_id.value)
        try:
            player_id = PlayerId(entity_int)
        except Exception:
            # PlayerId 構築が失敗する entity (= NPC 等の非 player) は skip。
            _logger.debug(
                "SpotArrivalEncounterHandler: non-player entity skipped "
                "(entity_id=%s)",
                entity_int,
            )
            return

        spot_int = int(event.spot_id.value)
        try:
            spot_str_id = self._spot_str_id_resolver(spot_int)
        except Exception:
            _logger.exception(
                "SpotArrivalEncounterHandler: spot_str_id_resolver failed "
                "(spot_id=%s); skipping",
                spot_int,
            )
            return

        current_tick = self._safe_current_tick()
        if current_tick is None:
            _logger.debug(
                "SpotArrivalEncounterHandler: current_tick unavailable; "
                "skipping (player=%s, spot=%s)",
                entity_int,
                spot_str_id,
            )
            return

        key = EncounterKey.spot(spot_str_id)
        self._memory.observe(player_id, key, current_tick)

    def _safe_current_tick(self) -> Optional[int]:
        try:
            tick = self._current_tick_provider()
        except Exception:
            _logger.exception(
                "SpotArrivalEncounterHandler: current_tick_provider raised"
            )
            return None
        if not isinstance(tick, int) or isinstance(tick, bool):
            return None
        if tick < 0:
            return None
        return tick


__all__ = ["SpotArrivalEncounterHandler", "SpotStrIdResolver"]
