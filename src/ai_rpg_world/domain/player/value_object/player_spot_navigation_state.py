"""
PlayerSpotNavigationState: スポットグラフ上のプレイヤー移動状態（不変値オブジェクト）。

2D タイル用の PlayerNavigationState と独立に保持し、PlayerStatusAggregate がオプションで持つ。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

from ai_rpg_world.domain.player.exception.player_exceptions import SpotNavigationStateInvalidException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


@dataclass(frozen=True)
class PlayerSpotNavigationState:
    """スポットグラフ上の現在地・移動中経路・区間ティックを表す。"""

    current_spot_id: SpotId
    current_sub_location_id: Optional[SubLocationId]
    is_traveling: bool
    route: Tuple[SpotId, ...]
    leg_index: int
    leg_connection_ids: Tuple[ConnectionId, ...]
    leg_travel_ticks: Tuple[int, ...]
    ticks_remaining_on_current_leg: int

    @classmethod
    def at_rest(
        cls,
        spot_id: SpotId,
        sub_location_id: Optional[SubLocationId] = None,
    ) -> "PlayerSpotNavigationState":
        return cls(
            current_spot_id=spot_id,
            current_sub_location_id=sub_location_id,
            is_traveling=False,
            route=(),
            leg_index=0,
            leg_connection_ids=(),
            leg_travel_ticks=(),
            ticks_remaining_on_current_leg=0,
        )

    @classmethod
    def begin_travel(
        cls,
        route: Tuple[SpotId, ...],
        leg_connection_ids: Tuple[ConnectionId, ...],
        leg_travel_ticks: Tuple[int, ...],
    ) -> "PlayerSpotNavigationState":
        """経路と各区間の接続・ティック数から移動中状態を構築する。

        route[0] は現在地（グラフ上の entity 位置と一致していること）。
        移動開始時はサブロケーションはクリアされる。
        """
        if len(route) < 2:
            raise SpotNavigationStateInvalidException("経路は少なくとも2スポット必要です")
        if len(leg_connection_ids) != len(route) - 1:
            raise SpotNavigationStateInvalidException("区間数と接続IDの数が一致しません")
        if len(leg_travel_ticks) != len(leg_connection_ids):
            raise SpotNavigationStateInvalidException("区間数と travel_ticks の数が一致しません")
        for t in leg_travel_ticks:
            if t < 0:
                raise SpotNavigationStateInvalidException("travel_ticks は負にできません")
        return cls(
            current_spot_id=route[0],
            current_sub_location_id=None,
            is_traveling=True,
            route=route,
            leg_index=0,
            leg_connection_ids=leg_connection_ids,
            leg_travel_ticks=leg_travel_ticks,
            ticks_remaining_on_current_leg=leg_travel_ticks[0],
        )

    def with_sub_location(self, sub_id: Optional[SubLocationId]) -> "PlayerSpotNavigationState":
        """同一スポット内のサブロケーションのみ変更する。移動中は不可。"""
        if self.is_traveling:
            raise SpotNavigationStateInvalidException("移動中はサブロケーションを変更できません")
        return replace(self, current_sub_location_id=sub_id)

    def advance_one_world_tick(
        self,
    ) -> Tuple[Tuple[Tuple[ConnectionId, SpotId], ...], "PlayerSpotNavigationState"]:
        """1 ワールドティック分進める。

        Returns:
            (今ティックで発生するグラフ横断の列（順に move_entity）、新しい状態)
        """
        if not self.is_traveling:
            return (), self

        crossings: List[Tuple[ConnectionId, SpotId]] = []
        s = self

        if s.ticks_remaining_on_current_leg > 0:
            new_t = s.ticks_remaining_on_current_leg - 1
            if new_t > 0:
                return (), replace(s, ticks_remaining_on_current_leg=new_t)
            s = replace(s, ticks_remaining_on_current_leg=0)

        while s.is_traveling and s.ticks_remaining_on_current_leg == 0:
            cid = s.leg_connection_ids[s.leg_index]
            arrived = s.route[s.leg_index + 1]
            crossings.append((cid, arrived))

            if s.leg_index + 1 >= len(s.route) - 1:
                return tuple(crossings), PlayerSpotNavigationState.at_rest(arrived)

            next_leg = s.leg_index + 1
            next_ticks = s.leg_travel_ticks[next_leg]
            s = replace(
                s,
                current_spot_id=arrived,
                leg_index=next_leg,
                ticks_remaining_on_current_leg=next_ticks,
            )
            if next_ticks > 0:
                return tuple(crossings), s

        return tuple(crossings), s
