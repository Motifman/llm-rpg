"""PlayerCurrentStateDto 用のスポットグラフスナップショット構築"""

from __future__ import annotations

import logging
from typing import Callable, FrozenSet, Optional

from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphAtmosphereEntry,
    SpotGraphConnectionEntry,
    SpotGraphGroundItemEntry,
    SpotGraphInteractionEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphMonsterEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
    SpotGraphSubLocationEntry,
    SpotGraphTimeOfDayEntry,
    SpotGraphWeatherEntry,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import EntityNotInGraphException
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.spot_perception_service import SpotPerceptionService
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

from ai_rpg_world.domain.world.value_object.weather_state import WeatherState

logger = logging.getLogger(__name__)


def _has_failing_object_state_precondition(interaction, interior) -> bool:
    """interaction の OBJECT_STATE precondition が現在 失敗しているか判定する。

    第24回実験 (#343) で cockpit を 19 回 retry した silent failure の対策。
    OBJECT_STATE は「取り尽くした」「もう空だ」のような永続失敗を持つ唯一の
    precondition 種別。HAS_ITEM / TIME_OF_DAY / WEATHER 等のプレイヤー / 環境
    依存は対象外 (将来満たされ得るので隠さない)。

    True を返したら interaction は snapshot から落とす想定。reactive_binding
    で state が戻ったら次 tick で再表示されるので、respawn / cooldown 系の
    interaction は影響を受けない。
    """
    for cond in interaction.preconditions:
        if cond.condition_type != InteractionConditionTypeEnum.OBJECT_STATE:
            continue
        if cond.target_object_id is None or not cond.required_state:
            continue
        target = interior.get_object(cond.target_object_id)
        if target is None:
            continue
        for key, required_value in cond.required_state.items():
            if target.state.get(key) != required_value:
                return True
    return False


# PR #2 状態異常 surface: StatusEffectType.value → 日本語ラベル。
# enum.value (英語) のままだと LLM が「これは何の状態異常?」と混乱するので
# プロンプト表示用に日本語化する。未知の effect_type は value をそのまま出す。
_STATUS_EFFECT_LABELS: dict[str, str] = {
    "bleeding": "出血",
    "poison": "毒",
    "hypothermia": "低体温",
    "infected": "感染症",
    "regeneration": "回復",
    "exhausted": "疲労困憊",
    "stun": "気絶",
    "silence": "沈黙",
    "blind": "暗闇",
    "burn": "火傷",
    "freeze": "凍結",
    "sleep": "睡眠",
    "paralysis": "麻痺",
}

EntityNameResolver = Callable[[int], str]
WeatherProvider = Callable[[], Optional[WeatherState]]
WorldFlagsProvider = Callable[[], frozenset[str]]
OwnedItemSpecIdsProvider = Callable[[int], FrozenSet[ItemSpecId]]
# item_spec_id (int) → 表示名 (str) のラッパ。ground_items 表示で使う。
# 未解決時は空文字列 or "アイテム#N" のような fallback を返してよい。
ItemSpecNameResolver = Callable[[int], str]
# 現在 tick の TimeOfDay を返す provider。シナリオが昼夜サイクルを宣言して
# いなければ None を返す (= プロンプトに時刻行が出ない)。
TimeOfDayProvider = Callable[[], Optional[TimeOfDay]]
# モンスター個体 ID から「肉眼で観測できる範囲の view DTO」を返す resolver。
# 名前解決と内部 state の可視化（HP バケット化・behavior の日本語化）を application 層で行う。
# None を返した場合は builder 側で当該個体を snapshot から黙って除外する（既に死んで掃除されたケース等）。
MonsterViewProvider = Callable[[MonsterId], Optional[SpotGraphMonsterEntry]]


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
        monster_view_provider: Optional[MonsterViewProvider] = None,
        item_spec_name_resolver: Optional[ItemSpecNameResolver] = None,
        time_of_day_provider: Optional[TimeOfDayProvider] = None,
        item_state_resolver: Optional[Callable[[int], Optional[dict]]] = None,
        current_tick_provider: Optional[Callable[[], int]] = None,
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
        self._monster_view_provider = monster_view_provider
        self._item_spec_name_resolver = item_spec_name_resolver
        self._time_of_day_provider = time_of_day_provider
        # Phase D-3a: 地面アイテムの spoiled 表示用。instance_id → state dict
        # (None なら spoiled 不明)。None なら spoiled は常に False 扱いになり、
        # この拡張を使わないシナリオ (脱出ゲーム本編など) に無影響。
        self._item_state_resolver = item_state_resolver
        # PR #2 状態異常 surface: 残り tick 表示用 (None なら effect 名のみ表示)
        self._current_tick_provider = current_tick_provider
        self._perception = SpotPerceptionService()

    def _build_time_of_day_entry(self) -> Optional[SpotGraphTimeOfDayEntry]:
        """シナリオが昼夜サイクルを宣言していれば snapshot に現在時刻を載せる。

        provider が未設定 (= シナリオが day_night を宣言していない) なら None。
        provider が例外を投げるのは想定外。silent に握りつぶさず warning ログ
        を出した上で None を返し、プロンプトから時刻行を落とす safer fallback
        にする。
        """
        if self._time_of_day_provider is None:
            return None
        try:
            tod = self._time_of_day_provider()
        except Exception:
            logger.warning(
                "time_of_day_provider raised unexpectedly; skipping time_of_day in snapshot",
                exc_info=True,
            )
            return None
        if tod is None:
            return None
        return SpotGraphTimeOfDayEntry(
            phase_name=tod.phase_name,
            display_text=tod.display_text,
            is_dark=tod.is_dark,
        )

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
            traversable = conn.passage.traversable
            condition_text: str | None = None
            if not traversable:
                if conn.passage_conditions:
                    msgs = [pc.failure_message for pc in conn.passage_conditions if pc.failure_message]
                    condition_text = "；".join(msgs) if msgs else None
                if not condition_text and conn.description:
                    condition_text = conn.description
            connections.append(SpotGraphConnectionEntry(
                destination_spot_id=conn.to_spot_id.value,
                connection_name=conn.name,
                destination_spot_name=dest.name,
                is_passable=traversable,
                passage_condition_text=condition_text,
            ))
            status = "通行可" if traversable else "通行不可（音は届く可能性あり）"
            connection_lines.append(f"- {conn.name} → {dest.name}（{status}）")

        objects: list[SpotGraphObjectEntry] = []
        sub_locations: list[SpotGraphSubLocationEntry] = []
        sub_lines: list[str] = []
        obj_lines: list[str] = []
        ground_lines: list[str] = []
        ground_items: list[SpotGraphGroundItemEntry] = []

        # --- 知覚判定: 照明 + 光源 ---
        presence = graph.presence_at(spot_id)
        viewer_has_light = self._entity_has_light_source(player_id)
        spot_has_any_light_bearer = viewer_has_light or any(
            self._entity_has_light_source(int(other_eid))
            for other_eid in presence.present_entity_ids
            if other_eid != eid
        )
        # Phase: 夜 / 悪天候で屋外の視界を 1 段下げる。
        # provider が居なければ「明るい / 良天候」とみなす (= 既存挙動)。
        time_of_day_is_dark = False
        if self._time_of_day_provider is not None:
            try:
                tod = self._time_of_day_provider()
                if tod is not None:
                    time_of_day_is_dark = bool(tod.is_dark)
            except Exception:
                time_of_day_is_dark = False
        weather_obscures_vision = False
        if self._weather_provider is not None:
            try:
                ws = self._weather_provider()
                if ws is not None:
                    # STORM / FOG は視界減衰扱い。weather_type.value の文字列で
                    # 判定して enum 直接依存を避ける。RAIN は微減なので含めない。
                    wt = getattr(ws.weather_type, "value", None) or str(ws.weather_type)
                    weather_obscures_vision = wt in ("STORM", "FOG")
            except Exception:
                weather_obscures_vision = False
        effective_lighting = self._perception.compute_effective_lighting(
            node.atmosphere,
            spot_has_any_light_bearer,
            is_outdoor=node.is_outdoor,
            time_of_day_is_dark=time_of_day_is_dark,
            weather_obscures_vision=weather_obscures_vision,
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
                    # 第24回実験 #343 対策: cockpit の OBJECT_STATE 永続失敗 (= 取り尽くした)
                    # interaction が snapshot に出続けて search_cockpit を 19 回 retry した。
                    # interaction の OBJECT_STATE precondition が「現在 失敗」しているなら、
                    # 可能行動から落とす。reactive_binding で state が戻れば自動で再表示される
                    # (= 採取の respawn 等は影響を受けない、tick が進むと再び見える)。
                    # HAS_ITEM / TIME_OF_DAY / WEATHER 等の「プレイヤー側 / 環境側」失敗は
                    # 残す: 「flint を持っていれば狼煙を上げられる」の探索の手掛かりが
                    # 消えるのを防ぐため。
                    interactions = tuple(
                        SpotGraphInteractionEntry(
                            action_name=i.action_name,
                            display_label=i.display_label,
                        )
                        for i in obj.interactions
                        if not _has_failing_object_state_precondition(i, interior)
                    )
                    # Phase 4-E: スポットに居る全員から見える state を載せる。
                    # `obj.visible_state()` が hidden_state_keys を除外して返す。
                    visible_state = obj.visible_state()
                    objects.append(SpotGraphObjectEntry(
                        object_id=obj.object_id.value,
                        name=obj.name,
                        description=obj.resolved_description(
                            world_flags, viewer_entity_id=player_id
                        ),
                        interactions=interactions,
                        state=visible_state,
                    ))
                    # フォールバック行 (interactions DTO と整合): 同じく
                    # OBJECT_STATE 永続失敗の interaction は文面からも落とす。
                    actions = [
                        i.action_name
                        for i in obj.interactions
                        if not _has_failing_object_state_precondition(i, interior)
                    ]
                    act = " / ".join(actions) if actions else "—"
                    obj_lines.append(f"- {obj.name} [ {act} ]")

                for gi in interior.ground_items:
                    name = ""
                    if self._item_spec_name_resolver is not None:
                        try:
                            name = self._item_spec_name_resolver(gi.item_spec_id.value)
                        except Exception:
                            name = ""
                    if not name:
                        name = f"アイテム#{gi.item_instance_id.value}"
                    is_spoiled = False
                    if self._item_state_resolver is not None:
                        try:
                            state = self._item_state_resolver(gi.item_instance_id.value)
                            if state is not None:
                                is_spoiled = bool(state.get("spoiled"))
                        except Exception:
                            # resolver の例外は表示用なので silent fallback (False)。
                            # 永続的バグは観測 callback 経由でログに出るので、
                            # 表示パスで握り潰しても二重隠蔽にはならない。
                            is_spoiled = False
                    ground_items.append(SpotGraphGroundItemEntry(
                        item_instance_id=gi.item_instance_id.value,
                        item_spec_id=gi.item_spec_id.value,
                        name=name,
                        is_spoiled=is_spoiled,
                    ))
                    # 後方互換: 旧 ground_item_lines に名前付き行を残す。
                    ground_lines.append(f"- {name}")

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

        # スポットに居るモンスター個体。`can_see` が False（暗闇）の場合は
        # オブジェクトと同じく完全に隠す。
        # TODO(combat-pr): 暗闇では「攻撃されているのに current_state に居ない」
        # 状態が起き得る。戦闘ツール導入と同じ PR で「気配がする / うなり声」
        # の縮退表記に拡張する。それまでは戦闘ツールが入る前提なので gameplay
        # 上の不整合は発生しない（モンスターは行動できないため）。
        monsters_at_spot: list[SpotGraphMonsterEntry] = []
        if can_see and self._monster_view_provider is not None:
            monster_presence = graph.monster_presence_at(spot_id)
            for monster_id in sorted(
                monster_presence.present_monster_ids, key=lambda m: m.value
            ):
                view = self._monster_view_provider(monster_id)
                if view is None:
                    # 通常はターン中の race（aggregate と presence の一時的な
                    # 不整合）で None になり得るため、例外ではなく黙って除外
                    # する。ただし観測性のため debug ログだけは残す。バグ起因
                    # の不整合（presence に残り続ける monster_id）も同パスを
                    # 通るので、ログ無しでは追跡が難しくなる。
                    logger.debug(
                        "monster_view_provider returned None for monster_id=%s at spot_id=%s",
                        monster_id.value,
                        spot_id.value,
                    )
                    continue
                monsters_at_spot.append(view)

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

        # PR #2 状態異常 surface: active_effects を「出血 (残り 9 tick)」のような
        # 表記に変換して snapshot に載せる。current_tick_provider が未注入なら
        # 残り tick を省略する fallback (effect 名のみ)。
        active_effect_lines: tuple[str, ...] = ()
        if player is not None and player.active_effects:
            active_effect_lines = self._build_active_effect_lines(
                player.active_effects
            )

        # Phase 4-E: 行動者本人の自由 state を snapshot に載せる。HIDDEN を
        # 含む全項目を本人プロンプトに渡し、自己認識させる。第三者用の
        # snapshot は別経路 (recipient strategy + 専用 event) なのでここでは
        # 全部載せて問題ない。
        player_state_snapshot: dict = (
            dict(player.state) if player is not None else {}
        )

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
            monsters_at_spot=tuple(monsters_at_spot),
            inventory_items=inventory_items,
            ground_items=tuple(ground_items),
            time_of_day=self._build_time_of_day_entry(),
            need_lines=need_lines,
            ground_item_lines=ground_lines,
            connection_lines=connection_lines,
            sub_location_lines=sub_lines,
            object_lines=obj_lines,
            player_state=player_state_snapshot,
            active_effect_lines=active_effect_lines,
        )

    def _build_active_effect_lines(self, active_effects) -> tuple[str, ...]:
        """active_effects を「<日本語名> (残り N tick)」形式の行に変換する。

        current_tick_provider が未注入なら残り tick を省略する。
        provider が例外を投げた場合は warning log を出して残り tick を省略
        (snapshot 生成全体を落とさない安全側 fallback)。
        """
        current_tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                current_tick = int(self._current_tick_provider())
            except Exception:
                logger.warning(
                    "current_tick_provider raised unexpectedly; "
                    "omitting remaining-tick in active_effect_lines",
                    exc_info=True,
                )
                current_tick = None
        lines: list[str] = []
        for effect in active_effects:
            label = _STATUS_EFFECT_LABELS.get(
                effect.effect_type.value, effect.effect_type.value
            )
            if current_tick is not None:
                remaining = effect.expiry_tick.value - current_tick
                if remaining <= 0:
                    # まもなく cleanup される effect。最後の tick も surface する。
                    lines.append(f"{label} (まもなく治る)")
                else:
                    lines.append(f"{label} (残り {remaining} tick)")
            else:
                lines.append(label)
        return tuple(lines)

    def _entity_has_light_source(self, entity_id: int) -> bool:
        """エンティティが光源アイテムを持っているかを判定する。"""
        if not self._light_source_item_spec_ids:
            return False
        if self._owned_item_spec_ids_provider is None:
            return False
        owned = self._owned_item_spec_ids_provider(entity_id)
        return bool(self._light_source_item_spec_ids & owned)
