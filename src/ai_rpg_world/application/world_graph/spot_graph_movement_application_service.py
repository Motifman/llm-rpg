from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    SpotTravelAlreadyInProgressException,
    SpotTravelUnreachableException,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.service.spot_graph_navigation_service import (
    SpotGraphNavigationService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


@dataclass(frozen=True)
class SpotTravelTickAdvanceDto:
    """1 ティック進行後の横断結果（観測・ログ用）。"""

    entered_spot_ids: Tuple[SpotId, ...]


class SpotGraphMovementApplicationService:
    """スポットグラフ上のプレイヤー移動（経路設定・ティック進行）。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        navigation_service: SpotGraphNavigationService | None = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._navigation = navigation_service or SpotGraphNavigationService()

    @staticmethod
    def entity_id_for_player(player_id: PlayerId) -> EntityId:
        """プレイヤーとグラフ上エンティティの対応（同一の正の整数）。"""
        return EntityId.create(int(player_id))

    def move_to_sub_location(
        self,
        player_id: PlayerId,
        sub_location_id: SubLocationId | None,
    ) -> None:
        """同一スポット内のサブロケーションのみ変更する（スポット間移動中は不可）。"""
        graph = self._spot_graph_repository.find_graph()
        player = self._player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")
        entity_id = self.entity_id_for_player(player_id)
        spot_on_graph = graph.get_entity_spot(entity_id)
        player.ensure_spot_navigation_at_rest(spot_on_graph)
        nav = player.spot_navigation_state
        assert nav is not None
        if nav.current_spot_id != spot_on_graph:
            player.set_spot_navigation_state(
                PlayerSpotNavigationState.at_rest(spot_on_graph)
            )
        player.set_spot_sub_location(sub_location_id)
        self._player_status_repository.save(player)

    def start_travel_to_spot(
        self,
        player_id: PlayerId,
        destination_spot_id: SpotId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> None:
        """最短経路で移動を開始する。各区間の通行条件を開始時点で検証する。"""
        graph = self._spot_graph_repository.find_graph()
        player = self._player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")

        entity_id = self.entity_id_for_player(player_id)
        spot_on_graph = graph.get_entity_spot(entity_id)
        player.ensure_spot_navigation_at_rest(spot_on_graph)
        nav = player.spot_navigation_state
        assert nav is not None
        if nav.current_spot_id != spot_on_graph:
            player.set_spot_navigation_state(PlayerSpotNavigationState.at_rest(spot_on_graph))
            nav = player.spot_navigation_state
            assert nav is not None

        if nav.is_traveling:
            raise SpotTravelAlreadyInProgressException("既にスポット間移動中です")

        if nav.current_spot_id == destination_spot_id:
            self._player_status_repository.save(player)
            return

        route = self._navigation.calculate_route(
            graph, nav.current_spot_id, destination_spot_id
        )
        if not route:
            raise SpotTravelUnreachableException(
                f"到達不能: {nav.current_spot_id} → {destination_spot_id}"
            )

        leg_cids = []
        leg_ticks = []
        for i in range(len(route) - 1):
            a, b = route[i], route[i + 1]
            conn = graph.find_first_passable_connection_between(a, b)
            if conn is None:
                raise SpotTravelUnreachableException(f"接続なし: {a} → {b}")
            ok, reason = self._navigation.can_pass(conn, owned_item_spec_ids, world_flags)
            if not ok:
                raise ConnectionNotPassableException(reason or "通行できません")
            leg_cids.append(conn.connection_id)
            leg_ticks.append(conn.travel_ticks)

        new_nav = PlayerSpotNavigationState.begin_travel(
            route=tuple(route),
            leg_connection_ids=tuple(leg_cids),
            leg_travel_ticks=tuple(leg_ticks),
        )
        player.set_spot_navigation_state(new_nav)
        self._player_status_repository.save(player)

    def advance_spot_travel_one_tick(
        self,
        player_id: PlayerId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> SpotTravelTickAdvanceDto | None:
        """移動中なら 1 ティック進める。グラフの move_entity を順に適用する。"""
        graph = self._spot_graph_repository.find_graph()
        player = self._player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")
        nav = player.spot_navigation_state
        if nav is None or not nav.is_traveling:
            return None

        crossings, new_nav = nav.advance_one_world_tick()
        entity_id = self.entity_id_for_player(player_id)
        entered: list[SpotId] = []
        for cid, _dest in crossings:
            graph.move_entity(entity_id, cid, owned_item_spec_ids, world_flags)
            entered.append(graph.get_entity_spot(entity_id))

        player.set_spot_navigation_state(new_nav)
        self._spot_graph_repository.save(graph)
        self._player_status_repository.save(player)
        return SpotTravelTickAdvanceDto(entered_spot_ids=tuple(entered))
