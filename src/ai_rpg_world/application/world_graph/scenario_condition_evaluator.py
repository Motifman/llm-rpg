"""ScenarioEventCondition の評価器。

scenario_event の発火条件と reactive binding の predicate の両方で
共有される評価ロジックを 1 箇所に集約する。leaf 条件の各タイプと
合成条件 (NOT/AND/OR) を再帰評価する。
"""

from __future__ import annotations

import logging
import random
from typing import Callable, Optional

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)


_logger = logging.getLogger(__name__)
from ai_rpg_world.application.world_graph.spot_object_lookup import find_object_in_graph
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


class ScenarioConditionEvaluator:
    """ScenarioEventCondition を current_tick / graph / repos の文脈で評価する。

    内部状態を持たないので 1 つのインスタンスを scenario_event_stage と
    reactive_binding_stage で共有して構わない。
    """

    def __init__(
        self,
        *,
        world_flag_state: MutableWorldFlagState,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        weather_state_provider: Optional[Callable[[], WeatherState]] = None,
        random_source: Optional[random.Random] = None,
    ) -> None:
        self._world_flag_state = world_flag_state
        self._spot_interior_repository = spot_interior_repository
        self._player_status_repository = player_status_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        # WEATHER_IS 条件の評価に必要。None の場合 WEATHER_IS は常に False。
        # provider が返すのは WeatherState 互換オブジェクト
        # (.weather_type.value で天候名が取れる構造)。
        self._weather_state_provider = weather_state_provider
        # Phase D-1: PROBABILITY 評価用 RNG。未注入なら新しい random.Random()
        # で初期化するので非決定的。テストや再現実験では seed 注入で固定化する。
        self._random = random_source or random.Random()

    def evaluate(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> bool:
        """1 つの条件（leaf or 合成）を再帰的に評価する。"""
        return self._evaluate(cond, current_tick, graph)

    def evaluate_all(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> bool:
        """複数条件の暗黙 AND（全部真なら真）。"""
        return all(self._evaluate(c, current_tick, graph) for c in conditions)

    def _evaluate(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> bool:
        ctype = cond.condition_type
        # 合成条件
        if ctype == "NOT":
            return not self._evaluate(cond.children[0], current_tick, graph)
        if ctype == "AND":
            return all(self._evaluate(c, current_tick, graph) for c in cond.children)
        if ctype == "OR":
            if not cond.children:
                return False
            return any(self._evaluate(c, current_tick, graph) for c in cond.children)
        # leaf 条件
        # Phase D-1: PROBABILITY は他の leaf より先に処理する。理由は (a) 他の
        # 軸とは独立に毎評価で random を消費するので順序を明確にする (b) 評価
        # コストが高い state lookup を不要に走らせない。
        if ctype == "PROBABILITY":
            # __post_init__ で probability が None / 範囲外なら弾かれているので
            # ここでは float() しても安全。
            return self._random.random() < float(cond.probability)
        world_flags = self._world_flag_state.as_frozen_set()
        if ctype == "TICK_AT_LEAST":
            return cond.tick is not None and current_tick.value >= int(cond.tick)
        if ctype == "TICK_BETWEEN":
            if cond.tick_start is None or cond.tick_end is None:
                return False
            return int(cond.tick_start) <= current_tick.value <= int(cond.tick_end)
        if ctype == "FLAG_SET":
            return bool(cond.flag_name) and cond.flag_name in world_flags
        if ctype == "FLAG_NOT_SET":
            return bool(cond.flag_name) and cond.flag_name not in world_flags
        if ctype == "PLAYER_AT_SPOT":
            # TODO(#15): 現状は「誰かが居る」判定。「特定 entity だけ居る」を
            # 表現するには ScenarioEventCondition.entity_id 等の拡張が必要。
            if cond.spot_id is None:
                return False
            spot_id = SpotId.create(cond.spot_id)
            presence = graph.presence_at(spot_id)
            return bool(presence.present_entity_ids)
        if ctype == "OBJECT_STATE":
            if cond.object_id is None or cond.required_state is None:
                return False
            obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph, self._spot_interior_repository,
            )
            if obj is None:
                return False
            return all(obj.state.get(k) == v for k, v in cond.required_state.items())
        if ctype == "HAS_ITEM":
            if cond.item_spec_id is None:
                return False
            target_spec = cond.item_spec_id
            for status in self._player_status_repository.find_all():
                inv = self._player_inventory_repository.find_by_id(status.player_id)
                if inv is None:
                    continue
                owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)
                if any(spec.value == target_spec for spec in owned):
                    return True
            return False
        if ctype == "TICK_MODULO":
            if cond.tick_modulo is None or cond.tick_modulo <= 0:
                return False
            phase = cond.tick_phase or 0
            return current_tick.value % cond.tick_modulo == phase
        if ctype == "WEATHER_IS":
            # WEATHER_IS: 現在の天候タイプが weather_type と一致するか判定する。
            # weather_state_provider が None なら常に False（後方互換）。
            # provider 呼び出しの例外は隠蔽せず caller のバグとして surface する。
            if not cond.weather_type or self._weather_state_provider is None:
                return False
            state = self._weather_state_provider()
            return state.weather_type.value == cond.weather_type
        if ctype == "OBJECT_STATE_TICK_AT_LEAST":
            # 「対象 object の state[state_key] が tick 値で、そこから
            # ticks_offset 経過したか」を判定する。state_key の値は int 想定。
            # state_key が無い / 値が None の場合は「まだ起きていない」と
            # 解釈し、`treat_missing_as_passed` フラグで True/False を選ぶ
            # （default False = 経過判定不能なので fire しない）。
            # 値が int でも None でもない場合は作家ミスの可能性があるので
            # 警告ログを出して False。
            if (
                cond.object_id is None
                or not cond.state_key
                or cond.ticks_offset is None
            ):
                return False
            obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph, self._spot_interior_repository,
            )
            if obj is None:
                return False
            recorded_tick = obj.state.get(cond.state_key)
            if recorded_tick is None:
                # 「まだ起きていない」 sentinel。作家が `treat_missing_as_passed`
                # で意味を選択する。silent fallback を避けるためフラグを default
                # False（保守的）にしてある。
                return bool(cond.treat_missing_as_passed)
            if not isinstance(recorded_tick, int):
                # シナリオ作家が int でも None でもない値（文字列など）を
                # 入れていたケース。デバッグ困難になるので警告を出す。
                _logger.warning(
                    "OBJECT_STATE_TICK_AT_LEAST: state[%r] is not int or None "
                    "(got %s) for object_id=%s",
                    cond.state_key,
                    type(recorded_tick).__name__,
                    cond.object_id,
                )
                return False
            return current_tick.value >= recorded_tick + int(cond.ticks_offset)
        if ctype == "OBJECT_STATE_INT_AT_LEAST":
            # state[state_key] の整数値が threshold (= ticks_offset を流用) 以上か。
            # 採取の枯渇 (count >= N で永久に available=false) の判定に使う。
            # state_key 不在 / 値が int 以外 → 0 扱いで判定 (= 「まだ採取してない」状態)。
            if cond.object_id is None or not cond.state_key or cond.ticks_offset is None:
                return False
            obj = find_object_in_graph(
                SpotObjectId.create(cond.object_id), graph, self._spot_interior_repository,
            )
            if obj is None:
                return False
            current_value = obj.state.get(cond.state_key, 0)
            if not isinstance(current_value, int):
                current_value = 0
            return current_value >= int(cond.ticks_offset)
        # 未知の condition_type は False（既存挙動を維持）
        return False

