"""PlayerCurrentStateDto 用のスポットグラフスナップショット構築"""

from __future__ import annotations

from typing import Callable, FrozenSet, Optional

from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphAtmosphereEntry,
    SpotGraphConnectionEntry,
    SpotGraphInteractionEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
    SpotGraphSubLocationEntry,
    SpotGraphWeatherEntry,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import EntityNotInGraphException
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.spot_perception_service import SpotPerceptionService
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

from ai_rpg_world.domain.world.value_object.weather_state import WeatherState

EntityNameResolver = Callable[[int], str]
WeatherProvider = Callable[[], Optional[WeatherState]]
WorldFlagsProvider = Callable[[], frozenset[str]]
OwnedItemSpecIdsProvider = Callable[[int], FrozenSet[ItemSpecId]]


class SpotGraphCurrentStateBuilder:
    """グラフ・内部データ・プレイヤー状態からスナップショットを組み立てる。

    知覚フィルタを有効にするには、以下のパラメータをワイヤリング時に渡す:
    - ``light_source_item_spec_ids``: 光源として扱うアイテムのID集合
    - ``owned_item_spec_ids_provider``: エンティティIDからアイテム所持を返すコールバック
    これらが未設定の場合、照明フィルタは無効（全オブジェクト表示）となる。
    """

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
        *,
        entity_name_resolver: Optional[EntityNameResolver] = None,
        inventory_builder: Optional[Callable[[PlayerId], tuple]] = None,
        weather_provider: Optional[WeatherProvider] = None,
        world_flags_provider: Optional[WorldFlagsProvider] = None,
        light_source_item_spec_ids: FrozenSet[ItemSpecId] = frozenset(),
        owned_item_spec_ids_provider: Optional[OwnedItemSpecIdsProvider] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._player_status_repository = player_status_repository
        self._entity_name_resolver = entity_name_resolver
        self._inventory_builder = inventory_builder
        self._weather_provider = weather_provider
        self._world_flags_provider = world_flags_provider
        self._light_source_item_spec_ids = light_source_item_spec_ids
        self._owned_item_spec_ids_provider = owned_item_spec_ids_provider
        self._perception = SpotPerceptionService()

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
            condition_text: str | None = None
            if not conn.is_passable:
                if conn.passage_conditions:
                    msgs = [pc.failure_message for pc in conn.passage_conditions if pc.failure_message]
                    condition_text = "；".join(msgs) if msgs else None
                if not condition_text and conn.description:
                    condition_text = conn.description
            connections.append(SpotGraphConnectionEntry(
                destination_spot_id=conn.to_spot_id.value,
                connection_name=conn.name,
                destination_spot_name=dest.name,
                is_passable=conn.is_passable,
                passage_condition_text=condition_text,
            ))
            status = "通行可" if conn.is_passable else "通行不可（音は届く可能性あり）"
            connection_lines.append(f"- {conn.name} → {dest.name}（{status}）")

        objects: list[SpotGraphObjectEntry] = []
        sub_locations: list[SpotGraphSubLocationEntry] = []
        sub_lines: list[str] = []
        obj_lines: list[str] = []
        ground_lines: list[str] = []

        # --- 知覚判定: 照明 + 光源 ---
        presence = graph.presence_at(spot_id)
        viewer_has_light = self._entity_has_light_source(player_id)
        spot_has_any_light_bearer = viewer_has_light or any(
            self._entity_has_light_source(int(other_eid))
            for other_eid in presence.present_entity_ids
            if other_eid != eid
        )
        effective_lighting = self._perception.compute_effective_lighting(
            node.atmosphere, spot_has_any_light_bearer
        )
        can_see = self._perception.can_see_objects(effective_lighting)

        # 光源持ちの名前を解決（知覚テキスト用）
        light_bearer_name: str | None = None
        if not viewer_has_light and spot_has_any_light_bearer and self._entity_name_resolver:
            for other_eid in presence.present_entity_ids:
                if other_eid != eid and self._entity_has_light_source(int(other_eid)):
                    try:
                        light_bearer_name = self._entity_name_resolver(int(other_eid))
                    except Exception:
                        light_bearer_name = None
                    break

        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        current_sub_id = (
            player.spot_navigation_state.current_sub_location_id
            if player is not None and player.spot_navigation_state is not None
            else None
        )
        if interior is not None:
            world_flags = (
                self._world_flags_provider() if self._world_flags_provider is not None else frozenset()
            )
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

            if can_see:
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
                        description=obj.resolved_description(
                            world_flags, viewer_entity_id=player_id
                        ),
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
            base_lighting = a.lighting
            perception_note = self._perception.describe_lighting_perception(
                base_lighting, effective_lighting, viewer_has_light, light_bearer_name
            )
            atmosphere = SpotGraphAtmosphereEntry(
                lighting=effective_lighting.name,
                sound_ambient=a.sound_ambient,
                temperature=a.temperature.name,
                smell=a.smell,
                perception_note=perception_note,
            )

        nearby_entities: list[SpotGraphNearbyEntityEntry] = []
        for other_eid in presence.present_entity_ids:
            if other_eid != eid:
                name = ""
                if self._entity_name_resolver is not None:
                    try:
                        name = self._entity_name_resolver(int(other_eid))
                    except Exception:
                        name = f"不明({int(other_eid)})"
                nearby_entities.append(SpotGraphNearbyEntityEntry(
                    entity_id=int(other_eid),
                    display_name=name,
                ))

        inventory_items: tuple[SpotGraphInventoryItemEntry, ...] = ()
        if self._inventory_builder is not None:
            inventory_items = self._inventory_builder(PlayerId(player_id))

        weather: SpotGraphWeatherEntry | None = None
        if node.is_outdoor and self._weather_provider is not None:
            ws = self._weather_provider()
            if ws is not None:
                weather = SpotGraphWeatherEntry(
                    weather_type=ws.weather_type.value,
                    weather_intensity=ws.intensity,
                    is_outdoor=True,
                )

        # エージェントの欲求状態
        need_lines: tuple[str, ...] = ()
        if player is not None:
            need_lines = player.needs.describe_all()

        return SpotGraphPlayerSnapshotDto(
            current_spot_id=spot_id.value,
            current_spot_name=node.name,
            current_spot_description=node.description,
            travel_status_line=travel_line,
            connections=tuple(connections),
            objects=tuple(objects),
            sub_locations=tuple(sub_locations),
            atmosphere=atmosphere,
            weather=weather,
            nearby_entities=tuple(nearby_entities),
            inventory_items=inventory_items,
            need_lines=need_lines,
            ground_item_lines=ground_lines,
            connection_lines=connection_lines,
            sub_location_lines=sub_lines,
            object_lines=obj_lines,
        )

    def _entity_has_light_source(self, entity_id: int) -> bool:
        """エンティティが光源アイテムを持っているかを判定する。"""
        if not self._light_source_item_spec_ids:
            return False
        if self._owned_item_spec_ids_provider is None:
            return False
        owned = self._owned_item_spec_ids_provider(entity_id)
        return bool(self._light_source_item_spec_ids & owned)
