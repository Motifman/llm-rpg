"""PlayerCurrentStateDto 用のスポットグラフスナップショット構築"""

from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphAtmosphereEntry,
    SpotGraphConnectionEntry,
    SpotGraphInteractionEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
    SpotGraphSubLocationEntry,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import EntityNotInGraphException
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


class SpotGraphCurrentStateBuilder:
    """グラフ・内部データ・プレイヤー状態からスナップショットを組み立てる。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._player_status_repository = player_status_repository

    def build_snapshot(self, player_id: int) -> SpotGraphPlayerSnapshotDto | None:
        """プレイヤーがグラフに載っていない場合は None。"""
        graph = self._spot_graph_repository.find_graph()
        eid = EntityId.create(player_id)
        try:
            spot_id = graph.get_entity_spot(eid)
        except EntityNotInGraphException:
            return None

        node = graph.get_spot(spot_id)
        player = self._player_status_repository.find_by_id(PlayerId(player_id))
        travel_line: str | None = None
        if player is not None and player.spot_navigation_state is not None:
            nav = player.spot_navigation_state
            if nav.is_traveling:
                dest = nav.route[-1] if nav.route else spot_id
                travel_line = (
                    f"スポット間移動中（残りティック概算: 各区間 {nav.ticks_remaining_on_current_leg} など）"
                    f" → 目的地: {graph.get_spot(dest).name}"
                )

        connections: list[SpotGraphConnectionEntry] = []
        connection_lines: list[str] = []
        for conn in graph.iter_outgoing_connections_from(spot_id):
            dest = graph.get_spot(conn.to_spot_id)
            connections.append(SpotGraphConnectionEntry(
                destination_spot_id=conn.to_spot_id.value,
                connection_name=conn.name,
                destination_spot_name=dest.name,
                is_passable=conn.is_passable,
            ))
            status = "通行可" if conn.is_passable else "通行不可（音は届く可能性あり）"
            connection_lines.append(f"- {conn.name} → {dest.name}（{status}）")

        objects: list[SpotGraphObjectEntry] = []
        sub_locations: list[SpotGraphSubLocationEntry] = []
        sub_lines: list[str] = []
        obj_lines: list[str] = []
        ground_lines: list[str] = []

        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        current_sub_id = (
            player.spot_navigation_state.current_sub_location_id
            if player is not None and player.spot_navigation_state is not None
            else None
        )
        if interior is not None:
            for sl in interior.sub_locations:
                is_current = current_sub_id is not None and current_sub_id == sl.sub_location_id
                sub_locations.append(SpotGraphSubLocationEntry(
                    sub_location_id=sl.sub_location_id.value,
                    name=sl.name,
                    is_current=is_current,
                    is_hidden=sl.is_hidden,
                ))
                here = "（現在ここ）" if is_current else ""
                hidden = "（未発見）" if sl.is_hidden else ""
                sub_lines.append(f"- {sl.name}{here}{hidden}")

            for obj in interior.objects:
                if not obj.is_visible:
                    continue
                interactions = tuple(
                    SpotGraphInteractionEntry(
                        action_name=i.action_name,
                        display_label=i.display_label,
                    )
                    for i in obj.interactions
                )
                objects.append(SpotGraphObjectEntry(
                    object_id=obj.object_id.value,
                    name=obj.name,
                    description=obj.description,
                    interactions=interactions,
                ))
                actions = [i.action_name for i in obj.interactions]
                act = " / ".join(actions) if actions else "—"
                obj_lines.append(f"- {obj.name} [ {act} ]")

            for gi in interior.ground_items:
                ground_lines.append(f"- 地面: item_instance={gi.item_instance_id}")

        atmosphere: SpotGraphAtmosphereEntry | None = None
        if node.atmosphere is not None:
            a = node.atmosphere
            atmosphere = SpotGraphAtmosphereEntry(
                lighting=a.lighting.name,
                sound_ambient=a.sound_ambient,
                temperature=a.temperature.name,
                smell=a.smell,
            )

        nearby_entities: list[SpotGraphNearbyEntityEntry] = []
        presence = graph.presence_at(spot_id)
        for other_eid in presence.present_entity_ids:
            if other_eid != eid:
                nearby_entities.append(SpotGraphNearbyEntityEntry(entity_id=int(other_eid)))

        return SpotGraphPlayerSnapshotDto(
            current_spot_name=node.name,
            current_spot_description=node.description,
            travel_status_line=travel_line,
            connections=tuple(connections),
            objects=tuple(objects),
            sub_locations=tuple(sub_locations),
            atmosphere=atmosphere,
            nearby_entities=tuple(nearby_entities),
            ground_item_lines=ground_lines,
            connection_lines=connection_lines,
            sub_location_lines=sub_lines,
            object_lines=obj_lines,
        )
