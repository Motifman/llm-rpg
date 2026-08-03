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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotInGraphException,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


#: この評価器が実際に判定できる条件の種類。
#:
#: **読み込み時の照合に使う。** これが無かったとき、綴りを間違えた条件は
#: 黙って読み込みを通り、``_evaluate`` の末尾で False に落ちていた。
#:
#:     {"condition_type": "TICK_AT_LEATS", "value": 3}
#:     → 読み込みが通り、この出来事は永久に発火しない
#:
#: 誰も気づけない。妨害のように条件を大量に書く機能では、1 文字の違いが
#: 「なぜか何も起きない」になる。
#:
#: **分岐を足したらここにも足すこと。** 足し忘れは網羅テストが落とす
#: (モジュールの本文から ``ctype == "..."`` を拾って突き合わせている)。
KNOWN_CONDITION_TYPES: frozenset = frozenset({
    # 合成
    "NOT", "AND", "OR",
    # 時刻
    "TICK_AT_LEAST", "TICK_BETWEEN", "TICK_MODULO",
    # 世界フラグ
    "FLAG_SET", "FLAG_NOT_SET",
    # 位置・所持・世界フェーズ
    "PLAYER_AT_SPOT", "PLAYERS_AT_SPOT", "HAS_ITEM", "GAME_PHASE_IS",
    # オブジェクトの状態
    "OBJECT_STATE", "OBJECT_STATE_TICK_AT_LEAST", "OBJECT_STATE_INT_AT_LEAST",
    # 環境
    "WEATHER_IS",
    # 確率
    "PROBABILITY",
})


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
        game_phase_provider: Optional[Callable[[], GamePhase]] = None,
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
        # GAME_PHASE_IS は production で唯一の GamePhaseStore から読む。
        # 条件を使うのに未配線なら False へ縮退させず、構成ミスとして止める。
        self._game_phase_provider = game_phase_provider
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
        return self._evaluate(cond, current_tick, graph, target_player_id=None)

    def evaluate_for_player(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> bool:
        """対象プレイヤーの文脈で 1 条件を評価する。

        ``PLAYER_AT_SPOT`` や ``HAS_ITEM`` を世界全体ではなく指定した本人へ
        絞る。対象を渡し忘れたときに従来の世界条件へ縮退しないよう、入口で
        ``PlayerId`` を必須にする。
        """
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        return self._evaluate(cond, current_tick, graph, target_player_id)

    def evaluate_all(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> bool:
        """複数条件の暗黙 AND（全部真なら真）。"""
        return all(
            self._evaluate(c, current_tick, graph, target_player_id=None)
            for c in conditions
        )

    def evaluate_all_for_player(
        self,
        conditions: tuple[ScenarioEventCondition, ...],
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        *,
        target_player_id: PlayerId,
    ) -> bool:
        """対象プレイヤーの文脈で複数条件を暗黙の AND として評価する。"""
        if not isinstance(target_player_id, PlayerId):
            raise TypeError("target_player_id must be PlayerId")
        return all(
            self._evaluate(c, current_tick, graph, target_player_id)
            for c in conditions
        )

    def _evaluate(
        self,
        cond: ScenarioEventCondition,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
        target_player_id: Optional[PlayerId],
    ) -> bool:
        ctype = cond.condition_type
        # 合成条件
        if ctype == "NOT":
            return not self._evaluate(
                cond.children[0], current_tick, graph, target_player_id
            )
        if ctype == "AND":
            return all(
                self._evaluate(c, current_tick, graph, target_player_id)
                for c in cond.children
            )
        if ctype == "OR":
            if not cond.children:
                return False
            return any(
                self._evaluate(c, current_tick, graph, target_player_id)
                for c in cond.children
            )
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
            if cond.spot_id is None:
                return False
            if target_player_id is not None:
                try:
                    current_spot = graph.get_entity_spot(
                        EntityId.create(int(target_player_id))
                    )
                except EntityNotInGraphException:
                    return False
                return current_spot == SpotId.create(cond.spot_id)
            # 世界条件の既存意味は「誰かが居る」。scenario_event / reactive
            # binding は対象者を渡さないため、この分岐を従来どおり保つ。
            spot_id = SpotId.create(cond.spot_id)
            presence = graph.presence_at(spot_id)
            return bool(presence.present_entity_ids)
        if ctype == "PLAYERS_AT_SPOT":
            if cond.spot_id is None:
                return False
            required = (
                cond.required_player_count
                if cond.required_player_count is not None
                else 2
            )
            if (
                isinstance(required, bool)
                or not isinstance(required, int)
                or required <= 0
            ):
                return False
            # interaction 側の PLAYERS_AT_SPOT と同じ意味にする。
            # graph の在席だけを出所とし、down 状態も人数に含む。
            present = graph.presence_at(
                SpotId.create(cond.spot_id)
            ).present_entity_ids
            return len(present) >= required
        if ctype == "GAME_PHASE_IS":
            if not cond.game_phase:
                return False
            if self._game_phase_provider is None:
                raise RuntimeError(
                    "GAME_PHASE_IS requires game_phase_provider wiring"
                )
            return self._game_phase_provider().value == cond.game_phase
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
            if target_player_id is not None:
                inv = self._player_inventory_repository.find_by_id(target_player_id)
                if inv is None:
                    return False
                owned = collect_owned_item_spec_ids_from_inventory(
                    inv, self._item_repository
                )
                return any(spec.value == target_spec for spec in owned)
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
