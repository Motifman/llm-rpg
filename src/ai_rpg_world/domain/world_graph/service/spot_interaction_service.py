from __future__ import annotations

from collections import Counter
from typing import FrozenSet, Mapping, Optional, Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InsufficientEffectItemsException,
    InteractionNotAllowedException,
    InteractionNotFoundException,
    UnknownSpotObjectException,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import InteractionCondition
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.interaction_execution_result import InteractionExecutionResult
from ai_rpg_world.domain.world_graph.value_object.predicate_result import (
    PredicateResult,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_context import (
    ItemSpecCountsPredicateContext,
    OwnedItemSpecsPredicateContext,
    StateValuesPredicateContext,
    WorldFlagPredicateContext,
    WeatherTypePredicateContext,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_predicate import (
    FlagSetPredicate,
    ItemSpecCountAtLeastPredicate,
    ItemSpecOwnedPredicate,
    StateIntAtLeastPredicate,
    StateValuesMatchPredicate,
    WeatherTypeIsPredicate,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.service.players_at_spot_condition import (
    evaluate_players_at_spot,
)
from ai_rpg_world.domain.world_graph.service.scenario_predicate_evaluator import (
    ScenarioPredicateEvaluator,
)
from ai_rpg_world.domain.world_graph.service.stock_pool_regen import (
    compute_stock_regen,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)


class SpotInteractionService:
    """スポット内オブジェクト操作（リポジトリ非依存）"""

    def __init__(
        self,
        effect_service: Optional[WorldGraphEffectService] = None,
        predicate_evaluator: Optional[ScenarioPredicateEvaluator] = None,
    ) -> None:
        self._effect_service = effect_service or WorldGraphEffectService()
        self._predicate_evaluator = predicate_evaluator or ScenarioPredicateEvaluator()

    def find_interaction(self, spot_object: SpotObject, action_name: str) -> Optional[InteractionDef]:
        for idef in spot_object.interactions:
            if idef.action_name == action_name:
                return idef
        return None

    def can_interact(self, *args, **kwargs) -> Tuple[bool, Optional[str]]:
        """`evaluate_preconditions` の (成否, 理由) だけを返す薄いラッパー。

        #380 で「どの条件で落ちたか」も返す必要が出たが、``can_interact`` は
        テストを含め 64 箇所から呼ばれている。**戻り値を増やすと呼び出し側が全部
        壊れる**ので、richer な `evaluate_preconditions` を新設してこちらを
        委譲にした。失敗条件が要る呼び出しだけ新しい方を使う。
        """
        ok, reason, _failed = self.evaluate_preconditions(*args, **kwargs)
        return ok, reason

    def evaluate_preconditions(
        self,
        interaction: InteractionDef,
        spot_object: Optional[SpotObject],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        acting_item_aggregate: Optional["ItemAggregate"] = None,
        target_item_aggregate: Optional["ItemAggregate"] = None,
        acting_player_status: Optional["PlayerStatusAggregate"] = None,
        target_player_status: Optional["PlayerStatusAggregate"] = None,
        target_owned_item_spec_ids: Optional[FrozenSet[ItemSpecId]] = None,
        current_time_of_day_phase: Optional[str] = None,
        current_weather_type: Optional[str] = None,
        current_tick: Optional[WorldTick] = None,
        current_effective_lighting: Optional[LightingEnum] = None,
        current_spot_id: Optional[SpotId] = None,
        interior: Optional[SpotInterior] = None,
    ) -> Tuple[bool, Optional[str], Optional[InteractionCondition]]:
        """共通評価結果を、#1050 で公開した3要素へ射影する互換入口。"""
        result = self.evaluate_preconditions_result(
            interaction,
            spot_object,
            owned_item_spec_ids,
            world_flags,
            spot_presence_count=spot_presence_count,
            interaction_parameters=interaction_parameters,
            owned_item_spec_counts=owned_item_spec_counts,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
            target_player_status=target_player_status,
            target_owned_item_spec_ids=target_owned_item_spec_ids,
            current_time_of_day_phase=current_time_of_day_phase,
            current_weather_type=current_weather_type,
            current_tick=current_tick,
            current_effective_lighting=current_effective_lighting,
            current_spot_id=current_spot_id,
            interior=interior,
        )
        return (
            result.is_satisfied,
            result.failure_message,
            result.failed_predicate,
        )

    def evaluate_preconditions_result(
        self,
        interaction: InteractionDef,
        spot_object: Optional[SpotObject],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        acting_item_aggregate: Optional["ItemAggregate"] = None,
        target_item_aggregate: Optional["ItemAggregate"] = None,
        acting_player_status: Optional["PlayerStatusAggregate"] = None,
        # 対人 interaction の対象プレイヤー。acting_item / target_item の
        # 並置と同型で、対象側の条件 (行動不能かどうか等) を評価するために使う。
        target_player_status: Optional["PlayerStatusAggregate"] = None,
        # 対人 interaction の対象プレイヤーの所持アイテム。TARGET_HAS_ITEM /
        # TARGET_HAS_NO_ITEM の判定材料。None は「渡っていない」で、対象の
        # 所持条件は silent pass させず拒否する (渡し忘れで、持っていない相手
        # から奪えてしまうのを防ぐ)。
        target_owned_item_spec_ids: Optional[FrozenSet[ItemSpecId]] = None,
        # PR4: 時間帯 / 天候 condition の評価用。None なら該当 condition は
        # 「provider 不在」として fail する (silent skip を避けるため明示的に拒否)。
        current_time_of_day_phase: Optional[str] = None,
        current_weather_type: Optional[str] = None,
        # 備蓄プール (OBJECT_STOCK_AT_LEAST) の lazy 再生算出に使う現在 tick。
        # None のときは再生なし (= 記録済み stock をそのまま使う) にフォールバック。
        current_tick: Optional[WorldTick] = None,
        # PR 3: 場所条件の評価用。いずれも None なら該当 condition は拒否する
        # (provider 不在を silent pass させない — TIME_OF_DAY と同じ判断)。
        #   current_effective_lighting: SpotPerceptionService で合成済みの照明。
        #     spot の静的 atmosphere ではなく、昼夜・天候・光源持ちまで含む値。
        #   current_spot_id: 行為者の現在地。
        current_effective_lighting: Optional[LightingEnum] = None,
        current_spot_id: Optional[SpotId] = None,
        interior: Optional[SpotInterior] = None,
    ) -> PredicateResult[InteractionCondition]:
        """前提条件を宣言順に評価し、最初の不成立を構造化して返す。"""
        # Phase 4-B: 同一 instance を acting / target 両方として渡すのは
        # wiring バグ。precondition 段階で弾く（apply_effects と同じガード）。
        if (
            acting_item_aggregate is not None
            and acting_item_aggregate is target_item_aggregate
        ):
            raise ValueError(
                "acting_item_aggregate and target_item_aggregate must be distinct "
                "instances; passing the same aggregate as both indicates a wiring bug"
            )
        # `owned_item_spec_counts` が渡されない場合は「frozenset から各 1 個」
        # でフォールバックする（required_quantity=1 の既存挙動と互換）。
        # ただし precondition のいずれかが required_quantity > 1 を要求する
        # のに counts が無いと silent wrong answer になるので、その場合は
        # 早期に明示的なエラーで弾く（pre-release のため後方互換は不要）。
        if owned_item_spec_counts is None:
            # counts が要るのは「所持アイテム数」を見る condition だけ。
            # OBJECT_STOCK_AT_LEAST 等は required_quantity>1 を別用途 (備蓄量)
            # で使い owned_item_spec_counts を参照しないので、対象から除く。
            _item_count_conditions = (
                InteractionConditionTypeEnum.HAS_ITEM,
                InteractionConditionTypeEnum.HAS_ITEMS,
            )
            needs_counts = any(
                c.required_quantity > 1
                and c.condition_type in _item_count_conditions
                for c in interaction.preconditions
            )
            if needs_counts:
                raise ValueError(
                    "owned_item_spec_counts is required when any precondition has "
                    "required_quantity > 1; pass count_owned_item_instances_by_spec(...)"
                )
            counts: Mapping[ItemSpecId, int] = {sid: 1 for sid in owned_item_spec_ids}
        else:
            counts = owned_item_spec_counts
        for index, cond in enumerate(interaction.preconditions):
            ok, msg = self._evaluate_condition(
                cond, spot_object, world_flags,
                spot_presence_count=spot_presence_count,
                interaction_parameters=interaction_parameters,
                owned_item_spec_counts=counts,
                acting_item_aggregate=acting_item_aggregate,
                target_item_aggregate=target_item_aggregate,
                acting_player_status=acting_player_status,
                target_player_status=target_player_status,
                target_owned_item_spec_ids=target_owned_item_spec_ids,
                current_time_of_day_phase=current_time_of_day_phase,
                current_weather_type=current_weather_type,
                current_tick=current_tick,
                current_effective_lighting=current_effective_lighting,
                current_spot_id=current_spot_id,
                interior=interior,
            )
            if not ok:
                return PredicateResult.not_satisfied(
                    failed_predicate=cond,
                    failed_path=(index,),
                    failure_message=msg,
                )
        return PredicateResult.satisfied()

    @staticmethod
    def _condition_item_spec_id(
        cond: InteractionCondition,
        interaction_parameters: Optional[dict],
    ) -> Optional[ItemSpecId]:
        """対象所持条件が判定する品目を決める。

        ``item_spec_id_parameter_key`` が書かれていれば実行時指定
        (``interaction_parameters`` の該当キー) を優先し、無ければ定義に
        固定された ``target_item_spec_id`` を使う。実行時指定でキーが欠けて
        いる / 数値でない場合は ``None`` を返し、呼び出し側が前提条件の
        不成立として扱う (例外にしない — 「相手がそれを持っていない」は
        普通に起きる状況である)。
        """
        key = cond.item_spec_id_parameter_key
        if key is None:
            return cond.target_item_spec_id
        raw = (interaction_parameters or {}).get(key)
        if raw is None:
            return None
        try:
            return ItemSpecId.create(int(raw))
        except (TypeError, ValueError):
            return None

    def _evaluate_condition(
        self,
        cond: InteractionCondition,
        spot_object: Optional[SpotObject],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
        owned_item_spec_counts: Mapping[ItemSpecId, int],
        acting_item_aggregate: Optional["ItemAggregate"] = None,
        target_item_aggregate: Optional["ItemAggregate"] = None,
        acting_player_status: Optional["PlayerStatusAggregate"] = None,
        # 対人 interaction の対象プレイヤー。acting_item / target_item の
        # 並置と同型で、対象側の条件 (行動不能かどうか等) を評価するために使う。
        target_player_status: Optional["PlayerStatusAggregate"] = None,
        target_owned_item_spec_ids: Optional[FrozenSet[ItemSpecId]] = None,
        current_time_of_day_phase: Optional[str] = None,
        current_weather_type: Optional[str] = None,
        current_tick: Optional[WorldTick] = None,
        current_effective_lighting: Optional[LightingEnum] = None,
        current_spot_id: Optional[SpotId] = None,
        interior: Optional[SpotInterior] = None,
    ) -> Tuple[bool, Optional[str]]:
        t = cond.condition_type
        condition_object = spot_object
        if cond.target_object_id is not None and interior is not None:
            condition_object = interior.get_object(cond.target_object_id)
        if t == InteractionConditionTypeEnum.ALWAYS:
            return True, None
        if t == InteractionConditionTypeEnum.HAS_ITEM:
            if cond.target_item_spec_id is None:
                return False, cond.failure_message or "HAS_ITEM に target_item_spec_id がありません"
            required = max(1, int(cond.required_quantity))
            owned = owned_item_spec_counts.get(cond.target_item_spec_id, 0)
            common_result = self._predicate_evaluator.evaluate(
                ItemSpecCountAtLeastPredicate(cond.target_item_spec_id, required),
                ItemSpecCountsPredicateContext(owned_item_spec_counts),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or (
                    f"必要なアイテムが足りません (必要: {required}, 所持: {owned})"
                    if required > 1
                    else "必要なアイテムを持っていません"
                )
            return True, None
        if t in (
            InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM,
        ):
            if target_owned_item_spec_ids is None:
                # 対象の所持が渡っていないのに対象の所持条件が書かれている。
                # 黙って成立させると、持っていない相手から奪えてしまう。
                return False, (
                    cond.failure_message or "この行為には対象プレイヤーが必要です"
                )
            spec_id = self._condition_item_spec_id(cond, interaction_parameters)
            if spec_id is None:
                # 実行時指定なのに参照キーが無い = 「相手の持ち物にその名前が
                # 見当たらなかった」。前提条件の不成立として返す。
                return False, (
                    cond.failure_message or "相手はそれを持っていない"
                )
            common_result = self._predicate_evaluator.evaluate(
                ItemSpecOwnedPredicate(spec_id),
                OwnedItemSpecsPredicateContext(target_owned_item_spec_ids),
            )
            owns = ScenarioPredicateEvaluator.require_satisfaction(common_result)
            wants_owned = t == InteractionConditionTypeEnum.TARGET_HAS_ITEM
            if owns is not wants_owned:
                return False, cond.failure_message or (
                    "相手はそれを持っていない" if wants_owned
                    else "相手はそれを持っている"
                )
            return True, None
        if t == InteractionConditionTypeEnum.TARGET_PLAYER_IS_INCAPACITATED:
            # 対象が行動不能 (倒れている or 死んでいる) であることを要求する。
            #
            # 「死んでいる」は蘇生不可の終局状態で、集約単体からは判定できない
            # (PlayerOutcomeRegistry が持つ)。ここでは HP 0 = 行動不能として扱う。
            # 死亡は HP 0 の部分集合なので、この判定で両方を覆える。
            if target_player_status is None:
                # 対象が渡っていないのに対象の条件が書かれている。provider 不在を
                # silent pass せず拒否する既存規約に合わせる。
                return False, (
                    cond.failure_message
                    or "この行為には対象プレイヤーが必要です"
                )
            if not target_player_status.is_down:
                return False, (
                    cond.failure_message
                    or "相手は動いている。この行為はできない"
                )
            return True, None
        if t == InteractionConditionTypeEnum.OBJECT_STATE:
            if condition_object is None:
                # 対人 interaction のように対象オブジェクトを持たない文脈。
                # 黙って True にすると「条件を書いたのに素通り」になるので拒否する。
                return False, (
                    cond.failure_message
                    or "この行為には対象オブジェクトが必要な条件が書かれています"
                )
            if cond.required_state is None:
                return False, cond.failure_message or "OBJECT_STATE に required_state がありません"
            common_result = self._predicate_evaluator.evaluate(
                StateValuesMatchPredicate(cond.required_state),
                StateValuesPredicateContext(condition_object.state),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or "オブジェクトの状態が条件を満たしません"
            return True, None
        if t == InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST:
            if condition_object is None:
                return False, (
                    cond.failure_message
                    or "この行為には対象オブジェクトが必要な条件が書かれています"
                )
            if not cond.state_key:
                return False, (
                    cond.failure_message
                    or "OBJECT_STATE_INT_AT_LEAST に state_key がありません"
                )
            required = max(1, int(cond.required_quantity))
            current = condition_object.state.get(cond.state_key, 0)
            if not isinstance(current, int):
                current = 0
            common_result = self._predicate_evaluator.evaluate(
                StateIntAtLeastPredicate(cond.state_key, required),
                StateValuesPredicateContext(condition_object.state),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or (
                    f"必要な量が足りません (必要: {required}, いま: {current})"
                )
            return True, None
        if t == InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST:
            if spot_object is None:
                return False, (
                    cond.failure_message
                    or "この行為には対象オブジェクトが必要な条件が書かれています"
                )
            # 備蓄プールの現在量を lazy に算出し、required_quantity 以上あるか判定。
            # 備蓄設定は object.state に持つ (stock / stock_capacity / stock_tick /
            # stock_refill_interval)。current_tick 未提供時は再生なし (記録済み
            # stock をそのまま) にフォールバックする。
            required = max(1, int(cond.required_quantity))
            state = spot_object.state
            now = int(current_tick.value) if current_tick is not None else int(
                state.get("stock_tick", 0)
            )
            result = compute_stock_regen(
                stock=int(state.get("stock", 0)),
                capacity=int(state.get("stock_capacity", 0)),
                stock_tick=int(state.get("stock_tick", 0)),
                refill_interval=int(state.get("stock_refill_interval", 0)),
                now=now,
            )
            if result.effective_stock < required:
                return False, cond.failure_message or "備蓄が足りません。時間が経てば回復する"
            return True, None
        if t == InteractionConditionTypeEnum.FLAG_SET:
            if not cond.flag_name:
                return False, cond.failure_message or "フラグ名がありません"
            result = self._predicate_evaluator.evaluate(
                FlagSetPredicate(cond.flag_name),
                WorldFlagPredicateContext(world_flags),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(result):
                return False, cond.failure_message or "必要なフラグが立っていません"
            return True, None
        if t == InteractionConditionTypeEnum.FLAG_NOT_SET:
            if not cond.flag_name:
                return False, cond.failure_message or "フラグ名がありません"
            result = self._predicate_evaluator.evaluate(
                FlagSetPredicate(cond.flag_name),
                WorldFlagPredicateContext(world_flags),
            )
            if ScenarioPredicateEvaluator.require_satisfaction(result):
                return False, cond.failure_message or "その操作はもう必要ありません"
            return True, None

        # --- 脱出ゲーム拡張 ---

        if t == InteractionConditionTypeEnum.PLAYERS_AT_SPOT:
            result = evaluate_players_at_spot(
                presence_count=spot_presence_count,
                required_player_count=cond.required_player_count,
            )
            if not result.is_satisfied:
                return False, cond.failure_message or (
                    f"このアクションには"
                    f"{result.required_player_count}人以上が必要です"
                )
            return True, None

        if t == InteractionConditionTypeEnum.PREPARED_ACTION:
            if not cond.prepared_action_id:
                return False, cond.failure_message or "準備アクションIDがありません"
            prefix = f"prepared:{cond.prepared_action_id}:"
            if not any(f.startswith(prefix) for f in world_flags):
                return False, cond.failure_message or "他のプレイヤーがまだ準備していません"
            return True, None

        if t == InteractionConditionTypeEnum.PUZZLE_INPUT_MATCH:
            if not cond.puzzle_input_key:
                return False, cond.failure_message or "パズル入力キーがありません"
            params = interaction_parameters or {}
            user_input = params.get(cond.puzzle_input_key)
            expected = cond.required_state or {}
            if "answer" not in expected:
                return False, cond.failure_message or "パズル答えが設定されていません"
            expected_value = expected["answer"]
            if user_input is None or str(user_input) != str(expected_value):
                return False, cond.failure_message or "入力が正しくありません"
            return True, None

        if t == InteractionConditionTypeEnum.ITEM_INSTANCE_STATE:
            # Phase 4-A: acting item instance の state[k] が required_state の
            # 全キー/値と一致しているかを判定する。
            # acting_item_aggregate を渡してこなかった場合は precondition
            # 失敗 (作家ミスを silent にしないため)。
            if cond.required_state is None:
                return False, cond.failure_message or "ITEM_INSTANCE_STATE に required_state がありません"
            if acting_item_aggregate is None:
                return False, (
                    cond.failure_message
                    or "ITEM_INSTANCE_STATE は acting item instance を必要とします (use_item 経路で評価される想定)"
                )
            common_result = self._predicate_evaluator.evaluate(
                StateValuesMatchPredicate(cond.required_state),
                StateValuesPredicateContext(acting_item_aggregate.state),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or "アイテムの状態が条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.TARGET_ITEM_INSTANCE_STATE:
            # Phase 4-B: target item instance (cross-instance interaction の作用先)
            # の state を判定する。acting 版と semantics は同じで対象だけが違う。
            if cond.required_state is None:
                return False, cond.failure_message or "TARGET_ITEM_INSTANCE_STATE に required_state がありません"
            if target_item_aggregate is None:
                return False, (
                    cond.failure_message
                    or "TARGET_ITEM_INSTANCE_STATE は target item instance を必要とします"
                )
            common_result = self._predicate_evaluator.evaluate(
                StateValuesMatchPredicate(cond.required_state),
                StateValuesPredicateContext(target_item_aggregate.state),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or "対象アイテムの状態が条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.HAS_ITEMS:
            if not cond.required_item_spec_ids:
                return False, cond.failure_message or "HAS_ITEMS に必要アイテムリストがありません"
            # required_quantity は各 spec に同じ値を適用する。
            # 種別ごとに別々の数量を要求したい場合は HAS_ITEM を複数回列挙する。
            required = max(1, int(cond.required_quantity))
            count_context = ItemSpecCountsPredicateContext(owned_item_spec_counts)
            for item_id in cond.required_item_spec_ids:
                common_result = self._predicate_evaluator.evaluate(
                    ItemSpecCountAtLeastPredicate(item_id, required),
                    count_context,
                )
                if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                    return False, cond.failure_message or "必要なアイテムが揃っていません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_NEED_AT_LEAST:
            # Phase 4-D-1: プレイヤーの欲求 (HUNGER / FATIGUE 等) が threshold
            # 以上なら成立。「空腹なときだけ食物が効く」のような表現に使う。
            if cond.need_type is None or cond.need_threshold is None:
                return False, cond.failure_message or (
                    "PLAYER_NEED_AT_LEAST には need_type と need_threshold が必要です"
                )
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_NEED_AT_LEAST は acting player status を必要とします"
                )
            try:
                need_type = NeedType(cond.need_type)
            except ValueError:
                return False, cond.failure_message or (
                    f"PLAYER_NEED_AT_LEAST の need_type が不正: {cond.need_type!r}"
                )
            need = acting_player_status.needs.get(need_type)
            if need is None:
                # プレイヤーがその need を持たない (= 0 とみなす)
                return False, cond.failure_message or "対応する need が登録されていません"
            if need.value < int(cond.need_threshold):
                return False, cond.failure_message or "プレイヤーの状態が条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_GOLD_AT_LEAST:
            # 「gold が threshold 以上なら成立」。gold を納める効果
            # (DEPOSIT_GOLD_TO_OBJECT) が支払いの途中で死なないための入口。
            # 凍結 (取引に出している額) はここでは見えない — application 層が
            # 永続化の前にもう一段のガードを持つ。
            if cond.gold_threshold is None:
                return False, cond.failure_message or (
                    "PLAYER_GOLD_AT_LEAST には gold_threshold が必要です"
                )
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_GOLD_AT_LEAST は acting player status を必要とします"
                )
            if acting_player_status.gold.value < int(cond.gold_threshold):
                return False, cond.failure_message or (
                    f"所持金が足りません ({int(cond.gold_threshold)}G 必要)"
                )
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_HP_RATIO_BELOW:
            # 「HP が hp_ratio 未満なら成立」。「HP 半分以下のときだけ強い薬草」
            # のような表現用。
            if cond.hp_ratio is None:
                return False, cond.failure_message or "PLAYER_HP_RATIO_BELOW には hp_ratio が必要です"
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_HP_RATIO_BELOW は acting player status を必要とします"
                )
            # `Hp.get_percentage()` は max_hp==0 で 0.0 を返す。本 precondition は
            # 「HP 不足を確認する」用途なので、max_hp==0 のときは「条件を満たさない
            # (=拒否)」が安全側。0.0 < hp_ratio で実際に True 判定されるとマズい
            # のでここでは max_hp==0 を別経路で弾く。
            if acting_player_status.hp.max_hp <= 0:
                return False, cond.failure_message or "プレイヤーの HP 条件を満たしません (max_hp 不正)"
            ratio = acting_player_status.hp.get_percentage()
            if ratio >= float(cond.hp_ratio):
                return False, cond.failure_message or "プレイヤーの HP 条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_HP_RATIO_AT_LEAST:
            # 「HP が hp_ratio 以上なら成立」。「HP 満タンに近いときだけ強行突破」
            # のような表現用。BELOW の鏡像。
            if cond.hp_ratio is None:
                return False, cond.failure_message or "PLAYER_HP_RATIO_AT_LEAST には hp_ratio が必要です"
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_HP_RATIO_AT_LEAST は acting player status を必要とします"
                )
            if acting_player_status.hp.max_hp <= 0:
                return False, cond.failure_message or "プレイヤーの HP 条件を満たしません (max_hp 不正)"
            ratio = acting_player_status.hp.get_percentage()
            if ratio < float(cond.hp_ratio):
                return False, cond.failure_message or "プレイヤーの HP 条件を満たしません"
            return True, None

        if t == InteractionConditionTypeEnum.PLAYER_STATE_IS:
            # Phase 4-D-2: 行動者プレイヤーの自由 state が required_state と
            # 全キー/値で一致するなら成立。「変装中のプレイヤーだけ」「呪い
            # 状態のときだけ」のような分岐用。
            if cond.required_state is None:
                return False, cond.failure_message or "PLAYER_STATE_IS に required_state がありません"
            if acting_player_status is None:
                return False, (
                    cond.failure_message
                    or "PLAYER_STATE_IS は acting player status を必要とします"
                )
            common_result = self._predicate_evaluator.evaluate(
                StateValuesMatchPredicate(cond.required_state),
                StateValuesPredicateContext(acting_player_status.state),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or "プレイヤーの状態が条件を満たしません"
            return True, None

        if t in (
            InteractionConditionTypeEnum.TIME_OF_DAY_IS,
            InteractionConditionTypeEnum.TIME_OF_DAY_IS_NOT,
        ):
            # PR4: 時間帯による行動制限。required_time_of_day_phase が
            # 現在 phase と一致するか (_IS) / 一致しないか (_IS_NOT) を判定。
            # provider 不在 (current_time_of_day_phase is None) は silent pass
            # を避けて拒否する。シナリオが TIME_OF_DAY 条件を書いたのに
            # day_night 宣言が無いケースを早期に surface するため。
            if not cond.required_time_of_day_phase:
                return False, cond.failure_message or (
                    f"{t.value} に required_time_of_day_phase がありません"
                )
            if current_time_of_day_phase is None:
                return False, cond.failure_message or (
                    f"{t.value} は day_night provider を必要とします"
                )
            matches = current_time_of_day_phase == cond.required_time_of_day_phase
            ok = (
                matches
                if t == InteractionConditionTypeEnum.TIME_OF_DAY_IS
                else not matches
            )
            if not ok:
                return False, cond.failure_message or (
                    f"現在の時刻帯ではこの行動はできない (要求: {cond.required_time_of_day_phase})"
                )
            return True, None

        if t in (
            InteractionConditionTypeEnum.WEATHER_IS,
            InteractionConditionTypeEnum.WEATHER_IS_NOT,
        ):
            # PR4: 天候による行動制限。required_weather_type が現在 weather と
            # 一致するか (_IS) / 一致しないか (_IS_NOT) を判定。
            if not cond.required_weather_type:
                return False, cond.failure_message or (
                    f"{t.value} に required_weather_type がありません"
                )
            if current_weather_type is None:
                return False, cond.failure_message or (
                    f"{t.value} は weather provider を必要とします"
                )
            try:
                required_weather = WeatherTypeEnum(cond.required_weather_type)
                current_weather = WeatherTypeEnum(current_weather_type)
            except (TypeError, ValueError):
                # loaderを迂回した不正値の単純比較は、既存API互換として残す。
                matches = current_weather_type == cond.required_weather_type
            else:
                common_result = self._predicate_evaluator.evaluate(
                    WeatherTypeIsPredicate(required_weather),
                    WeatherTypePredicateContext(current_weather),
                )
                matches = ScenarioPredicateEvaluator.require_satisfaction(
                    common_result
                )
            ok = (
                matches
                if t == InteractionConditionTypeEnum.WEATHER_IS
                else not matches
            )
            if not ok:
                return False, cond.failure_message or (
                    f"現在の天候ではこの行動はできない (要求: {cond.required_weather_type})"
                )
            return True, None

        if t == InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS:
            # PR 3: 対象プレイヤーの自由 state を判定する。PLAYER_STATE_IS の
            # 対象版で、「crew だけ殺せる」「まだ印が無い相手だけ」を書く。
            if cond.required_state is None:
                return False, cond.failure_message or (
                    "TARGET_PLAYER_STATE_IS に required_state がありません"
                )
            if target_player_status is None:
                return False, (
                    cond.failure_message
                    or "TARGET_PLAYER_STATE_IS は対象プレイヤーを必要とします"
                )
            common_result = self._predicate_evaluator.evaluate(
                StateValuesMatchPredicate(cond.required_state),
                StateValuesPredicateContext(target_player_status.state),
            )
            if not ScenarioPredicateEvaluator.require_satisfaction(common_result):
                return False, cond.failure_message or "相手の状態が条件を満たしません"
            return True, None

        if t in (
            InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
            InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT,
        ):
            # PR 3: 実効照明による制限。current_effective_lighting は
            # SpotPerceptionService で合成済みの値を application 層から受け取る
            # (spot の静的 atmosphere ではない)。未配線 (None) は silent pass を
            # 避けて拒否する — 明るい場所で暗所限定の行為が通るほうが害が大きい。
            if not cond.required_lighting:
                return False, cond.failure_message or (
                    f"{t.value} に required_lighting がありません"
                )
            if current_effective_lighting is None:
                return False, cond.failure_message or (
                    f"{t.value} は実効照明の解決を必要とします"
                )
            matches = current_effective_lighting.value == cond.required_lighting
            ok = (
                matches
                if t == InteractionConditionTypeEnum.SPOT_LIGHTING_IS
                else not matches
            )
            if not ok:
                return False, cond.failure_message or (
                    f"ここの明るさではこの行動はできない (要求: {cond.required_lighting})"
                )
            return True, None

        if t in (
            InteractionConditionTypeEnum.AT_SPOT_IS,
            InteractionConditionTypeEnum.AT_SPOT_IS_NOT,
        ):
            # PR 3: 行為者の現在地による制限。
            if cond.required_spot_id is None:
                return False, cond.failure_message or (
                    f"{t.value} に required_spot がありません"
                )
            if current_spot_id is None:
                return False, cond.failure_message or (
                    f"{t.value} は行為者の現在地を必要とします"
                )
            matches = current_spot_id == cond.required_spot_id
            ok = (
                matches
                if t == InteractionConditionTypeEnum.AT_SPOT_IS
                else not matches
            )
            if not ok:
                return False, cond.failure_message or "ここではこの行動はできない"
            return True, None

        return False, cond.failure_message or "未対応の前提条件です"

    def execute_interaction(
        self,
        interior: SpotInterior,
        object_id: SpotObjectId,
        action_name: str,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
        current_tick: Optional[WorldTick] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        acting_item_aggregate: Optional[ItemAggregate] = None,
        target_item_aggregate: Optional[ItemAggregate] = None,
        acting_player_status: Optional[PlayerStatusAggregate] = None,
        current_time_of_day_phase: Optional[str] = None,
        current_weather_type: Optional[str] = None,
        # PR-F: 看板の書き手名。WRITE_PLAYER_TEXT effect が object.state に
        # 保存するために effect_service まで配線する。
        acting_player_display_name: Optional[str] = None,
        # PR 3: 場所条件 (SPOT_LIGHTING_IS / AT_SPOT_IS) の評価用。
        current_effective_lighting: Optional[LightingEnum] = None,
        current_spot_id: Optional[SpotId] = None,
    ) -> InteractionExecutionResult:
        obj = interior.get_object(object_id)
        if obj is None:
            raise UnknownSpotObjectException(str(object_id))
        idef = self.find_interaction(obj, action_name)
        if idef is None:
            raise InteractionNotFoundException(f"{action_name} on {object_id}")
        precondition_result = self.evaluate_preconditions_result(
            idef, obj, owned_item_spec_ids, world_flags,
            spot_presence_count=spot_presence_count,
            interaction_parameters=interaction_parameters,
            owned_item_spec_counts=owned_item_spec_counts,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
            current_time_of_day_phase=current_time_of_day_phase,
            current_weather_type=current_weather_type,
            current_tick=current_tick,
            current_effective_lighting=current_effective_lighting,
            current_spot_id=current_spot_id,
            interior=interior,
        )
        if not precondition_result.is_satisfied:
            raise InteractionNotAllowedException(
                precondition_result.failure_message or "Interaction not allowed",
                failed_condition=precondition_result.failed_predicate,
            )

        self._require_effect_item_removals(
            interior=interior,
            acting_object=obj,
            effects=idef.effects,
            interaction_parameters=interaction_parameters,
            owned_item_spec_ids=owned_item_spec_ids,
            owned_item_spec_counts=owned_item_spec_counts,
        )

        effect_result = self._effect_service.apply_effects(
            interior=interior,
            acting_object=obj,
            effects=idef.effects,
            world_flags=world_flags,
            current_tick=current_tick,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
            interaction_parameters=interaction_parameters,
            acting_player_display_name=acting_player_display_name,
            owned_item_spec_counts=owned_item_spec_counts,
        )
        return InteractionExecutionResult(
            new_interior=effect_result.new_interior,
            new_flags=effect_result.new_flags,
            messages=effect_result.messages,
            action_display_label=idef.effective_display_label,
            item_spec_ids_to_grant=effect_result.item_spec_ids_to_grant,
            item_spec_ids_to_remove=effect_result.item_spec_ids_to_remove,
            damage_specs=effect_result.damage_specs,
            status_effect_specs=effect_result.status_effect_specs,
            teleport_specs=effect_result.teleport_specs,
            meeting_call_triggers=effect_result.meeting_call_triggers,
            room_occupancy_display_specs=effect_result.room_occupancy_display_specs,
            atmosphere_update_specs=effect_result.atmosphere_update_specs,
            create_connection_specs=effect_result.create_connection_specs,
            destroy_connection_specs=effect_result.destroy_connection_specs,
            satisfy_need_specs=effect_result.satisfy_need_specs,
            deposit_gold_specs=effect_result.deposit_gold_specs,
            passage_state_updates=effect_result.passage_state_updates,
            item_instance_state_changed=effect_result.item_instance_state_changed,
            target_item_instance_state_changed=effect_result.target_item_instance_state_changed,
            acting_player_state_changed=effect_result.acting_player_state_changed,
            direct_effects=effect_result.actor_direct_effects,
            public_observable_effects=effect_result.public_observable_effects,
        )

    def execute_declared_interaction(
        self,
        interior: SpotInterior,
        interaction: InteractionDef,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        effect_interior: Optional[SpotInterior] = None,
        spot_presence_count: int = 1,
        interaction_parameters: Optional[dict] = None,
        current_tick: Optional[WorldTick] = None,
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]] = None,
        acting_item_aggregate: Optional[ItemAggregate] = None,
        target_item_aggregate: Optional[ItemAggregate] = None,
        acting_player_status: Optional[PlayerStatusAggregate] = None,
        current_time_of_day_phase: Optional[str] = None,
        current_weather_type: Optional[str] = None,
        acting_player_display_name: Optional[str] = None,
        current_effective_lighting: Optional[LightingEnum] = None,
        current_spot_id: Optional[SpotId] = None,
    ) -> InteractionExecutionResult:
        """物体を暗黙対象にしない、登録簿由来の interaction を実行する。

        道具に宿る操作は ``InteractionDef`` を共有するが、操作元の
        ``SpotObject`` は存在しない。前提条件と効果の評価を物体経路と同じ
        サービスへ集約しつつ、``acting_object=None`` を明示して、対象物の
        省略を勝手に補わない。

        ``effect_interior`` は、明示対象の物体が行為者と別の部屋にある場合だけ
        application 層が渡す。前提条件は行為者の現在地で評価し、効果は対象物の
        所有室へ適用することで、遠隔の道具操作を黙って無効にしない。
        """
        precondition_result = self.evaluate_preconditions_result(
            interaction,
            None,
            owned_item_spec_ids,
            world_flags,
            spot_presence_count=spot_presence_count,
            interaction_parameters=interaction_parameters,
            owned_item_spec_counts=owned_item_spec_counts,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
            current_time_of_day_phase=current_time_of_day_phase,
            current_weather_type=current_weather_type,
            current_tick=current_tick,
            current_effective_lighting=current_effective_lighting,
            current_spot_id=current_spot_id,
            interior=interior,
        )
        if not precondition_result.is_satisfied:
            raise InteractionNotAllowedException(
                precondition_result.failure_message or "Interaction not allowed",
                failed_condition=precondition_result.failed_predicate,
            )
        self._require_effect_item_removals(
            interior=effect_interior or interior,
            acting_object=None,
            effects=interaction.effects,
            interaction_parameters=interaction_parameters,
            owned_item_spec_ids=owned_item_spec_ids,
            owned_item_spec_counts=owned_item_spec_counts,
        )
        effect_result = self._effect_service.apply_effects(
            interior=effect_interior or interior,
            acting_object=None,
            effects=interaction.effects,
            world_flags=world_flags,
            current_tick=current_tick,
            acting_item_aggregate=acting_item_aggregate,
            target_item_aggregate=target_item_aggregate,
            acting_player_status=acting_player_status,
            interaction_parameters=interaction_parameters,
            acting_player_display_name=acting_player_display_name,
            owned_item_spec_counts=owned_item_spec_counts,
        )
        return InteractionExecutionResult(
            new_interior=effect_result.new_interior,
            new_flags=effect_result.new_flags,
            messages=effect_result.messages,
            action_display_label=interaction.effective_display_label,
            item_spec_ids_to_grant=effect_result.item_spec_ids_to_grant,
            item_spec_ids_to_remove=effect_result.item_spec_ids_to_remove,
            damage_specs=effect_result.damage_specs,
            status_effect_specs=effect_result.status_effect_specs,
            teleport_specs=effect_result.teleport_specs,
            meeting_call_triggers=effect_result.meeting_call_triggers,
            room_occupancy_display_specs=effect_result.room_occupancy_display_specs,
            atmosphere_update_specs=effect_result.atmosphere_update_specs,
            create_connection_specs=effect_result.create_connection_specs,
            destroy_connection_specs=effect_result.destroy_connection_specs,
            satisfy_need_specs=effect_result.satisfy_need_specs,
            deposit_gold_specs=effect_result.deposit_gold_specs,
            passage_state_updates=effect_result.passage_state_updates,
            item_instance_state_changed=effect_result.item_instance_state_changed,
            target_item_instance_state_changed=effect_result.target_item_instance_state_changed,
            acting_player_state_changed=effect_result.acting_player_state_changed,
            direct_effects=effect_result.actor_direct_effects,
            public_observable_effects=effect_result.public_observable_effects,
        )

    def _require_effect_item_removals(
        self,
        *,
        interior: SpotInterior,
        acting_object: SpotObject | None,
        effects: Tuple[InteractionEffect, ...],
        interaction_parameters: Optional[dict],
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        owned_item_spec_counts: Optional[Mapping[ItemSpecId, int]],
    ) -> None:
        """状態変更や抽選より前に、行為者側の削除要求全量を検証する。"""
        counts = (
            owned_item_spec_counts
            if owned_item_spec_counts is not None
            else {item_spec_id: 1 for item_spec_id in owned_item_spec_ids}
        )
        requirements = self._effect_service.plan_item_removals(
            interior=interior,
            acting_object=acting_object,
            effects=effects,
            interaction_parameters=interaction_parameters,
            owned_item_spec_counts=owned_item_spec_counts,
        )
        required = Counter(requirements.actor_item_spec_ids)
        if any(
            counts.get(item_spec_id, 0) < quantity
            for item_spec_id, quantity in required.items()
        ):
            raise InsufficientEffectItemsException(
                "必要な未予約アイテムが足りないため、この行動は実行できない"
            )
