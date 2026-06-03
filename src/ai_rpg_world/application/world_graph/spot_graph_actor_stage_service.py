from __future__ import annotations

import logging
from typing import Dict, Iterable

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotInGraphException,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_actor_rule import (
    SpotGraphActorRule,
)


_logger = logging.getLogger(__name__)


class SpotGraphActorStageService:
    """tick ごとに Spot Graph 上の自律アクターを進める最小 stage。"""

    def __init__(
        self,
        *,
        spot_graph_repository: ISpotGraphRepository,
        actor_rules: Iterable[SpotGraphActorRule],
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._actor_rules = tuple(actor_rules)
        self._route_cursor: Dict[int, int] = {}

    def run(self, current_tick: WorldTick, world_flags: frozenset[str]) -> None:
        graph = self._spot_graph_repository.find_graph()
        changed = False
        for rule in self._actor_rules:
            if len(rule.patrol_route_spot_ids) < 2:
                continue
            move_every = max(1, int(rule.move_every_ticks))
            if current_tick.value % move_every != 0:
                continue
            if rule.triggered_by_flag and rule.triggered_by_flag not in world_flags:
                continue
            changed = self._try_move_actor(graph, rule) or changed
        if changed:
            self._spot_graph_repository.save(graph)

    def _try_move_actor(self, graph, rule: SpotGraphActorRule) -> bool:
        entity_id = EntityId.create(rule.entity_id)
        try:
            current_spot = graph.get_entity_spot(entity_id)
        except EntityNotInGraphException:
            # actor が graph から消えた (despawn / 死亡)。route_cursor を残すと、
            # 同じ entity_id が再 spawn したときに「途中から行動再開」する地味
            # バグになるので、ここで掃除する。
            self._route_cursor.pop(rule.entity_id, None)
            return False
        except Exception:
            # その他予期しない graph エラー (corrupt state / repository error) は
            # silent に握りつぶさず warning を残してから skip する。
            _logger.warning(
                "SpotGraphActorStageService: unexpected error reading entity_spot "
                "for entity_id=%s; skipping this tick",
                rule.entity_id,
                exc_info=True,
            )
            return False

        route = [SpotId.create(s) for s in rule.patrol_route_spot_ids]
        idx = self._route_cursor.get(rule.entity_id, 0)
        target = route[(idx + 1) % len(route)]
        if current_spot != route[idx]:
            for i, sid in enumerate(route):
                if sid == current_spot:
                    idx = i
                    self._route_cursor[rule.entity_id] = i
                    target = route[(i + 1) % len(route)]
                    break
        conn = graph.find_first_passable_connection_between(current_spot, target)
        if conn is None:
            return False
        graph.move_entity(
            entity_id=entity_id,
            connection_id=conn.connection_id,
            owned_item_spec_ids=frozenset[ItemSpecId](),
            world_flags=frozenset(),
        )
        self._route_cursor[rule.entity_id] = (idx + 1) % len(route)
        return True
