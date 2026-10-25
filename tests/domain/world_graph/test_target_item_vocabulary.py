"""「相手が何を持っているか」を条件に書け、奪う品目を実行時に選べる。

対人 interaction で奪う (take) を書くには 2 つが要る。

1. **相手の所持を見る条件**。既存の ``HAS_ITEM`` は行為者の所持しか見ない。
   相手が持っていないのを内部エラーで落とすと、LLM から見て学習できない
   失敗になる (「相手はそれを持っていない」は普通に起きる状況である)。
2. **奪う品目の実行時指定**。倒れた相手の所持品は prompt に見えている
   (PR #824) ので、LLM は品目を名指ししたい。定義に ``item_spec_id`` を
   固定で書くと、品目のぶんだけ action を並べることになり、設計 doc §3.2
   で棄却した「同じ行為の複製」そのものになる。

どちらも同じ約束で書く。条件は ``item_spec_id_parameter_key``、効果は
``parameters["item_spec_id_parameter"]`` で、``interaction_parameters`` の
どのキーを見るかを指す。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.effect_target import EffectTarget
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionEffectValidationException,
    ScenarioPredicateEvaluationException,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.predicate_result import PredicateResult

DRIFTWOOD = ItemSpecId.create(7)
FLINT = ItemSpecId.create(8)


def _check(cond: InteractionCondition, *, target_owned=None, params=None, actor_owned=frozenset()):
    """condition 1 件だけの interaction を評価して (ok, message) を返す。"""
    idef = InteractionDef(action_name="take", display_label="奪う", preconditions=(cond,), effects=())
    return SpotInteractionService().can_interact(
        idef,
        None,
        actor_owned,
        frozenset(),
        interaction_parameters=params,
        target_owned_item_spec_ids=target_owned,
    )


class TestTargetHasItem:
    """``TARGET_HAS_ITEM`` は行為者ではなく対象の所持を見る。"""

    @pytest.mark.parametrize(
        ("spec", "actor_owned"),
        [(DRIFTWOOD, frozenset()), (FLINT, frozenset({DRIFTWOOD}))],
    )
    def test_passes_when_target_owns_the_fixed_item(self, spec, actor_owned) -> None:
        """行為者が別品目を持つ場合も、対象が宣言された品目を持っていれば成立する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            target_item_spec_id=spec,
        )
        assert _check(cond, target_owned=frozenset({spec}), actor_owned=actor_owned) == (True, None)

    def test_delegates_target_ownership_to_common_evaluator(self) -> None:
        """対象者の所持集合を渡し、固定品目のmembershipだけを共通核へ委譲する。"""
        common = MagicMock()
        common.evaluate.return_value = PredicateResult.satisfied()
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            target_item_spec_id=DRIFTWOOD,
        )
        interaction = InteractionDef(
            action_name="take",
            display_label="奪う",
            preconditions=(condition,),
            effects=(),
        )

        ok, message = SpotInteractionService(predicate_evaluator=common).can_interact(
            interaction,
            None,
            frozenset(),
            frozenset(),
            target_owned_item_spec_ids=frozenset({DRIFTWOOD}),
        )

        assert (ok, message) == (True, None)
        predicate, context = common.evaluate.call_args.args
        assert predicate.item_spec_id == DRIFTWOOD
        assert context.owned_item_spec_ids == frozenset({DRIFTWOOD})

    @pytest.mark.parametrize("actor_owned", [frozenset(), frozenset({DRIFTWOOD})])
    def test_fails_with_a_learnable_message_when_target_lacks_it(self, actor_owned) -> None:
        """対象が持っていなければ、内部エラーではなく前提条件の不成立で返る。"""
        ok, msg = _check(
            cond=InteractionCondition(
                condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
                target_item_spec_id=DRIFTWOOD,
            ),
            target_owned=frozenset({FLINT}),
            actor_owned=actor_owned,
        )
        assert ok is False
        assert msg == "相手はそれを持っていない"

    @pytest.mark.parametrize(
        "condition_type",
        [
            InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM,
        ],
    )
    def test_rejects_when_target_inventory_was_not_provided(self, condition_type) -> None:
        """対象の所持が渡っていないのに対象の条件が書かれていたら拒否する。

        渡し忘れを黙って成立させると、持っていない相手から奪えてしまう。
        provider 不在を silent pass させない既存規約に合わせる。
        """
        ok, _ = _check(
            cond=InteractionCondition(
                condition_type=condition_type,
                target_item_spec_id=DRIFTWOOD,
            ),
            target_owned=None,
        )
        assert ok is False

    @pytest.mark.parametrize(
        ("key", "spec", "fixed"),
        [("item_spec_id", DRIFTWOOD, None), ("chosen_item", FLINT, DRIFTWOOD)],
    )
    def test_reads_the_spec_id_from_interaction_parameters(self, key, spec, fixed) -> None:
        """任意の参照キーと実行時の品目を読み、固定品目が併記されても実行時指定を優先する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            target_item_spec_id=fixed,
            item_spec_id_parameter_key=key,
        )
        assert _check(
            cond,
            target_owned=frozenset({spec}),
            params={"item_spec_id": 7, key: spec.value},
        ) == (True, None)

    def test_fails_when_the_named_parameter_is_absent(self) -> None:
        """参照するキーが ``interaction_parameters`` に無ければ不成立で返る。

        「相手の持ち物にその名前が見当たらなかった」ときにこの経路へ来る。
        """
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            item_spec_id_parameter_key="item_spec_id",
        )
        ok, msg = _check(cond, target_owned=frozenset({DRIFTWOOD}), params={})
        assert ok is False
        assert msg


class TestTargetHasNoItem:
    """``TARGET_HAS_NO_ITEM`` は否定形。"""

    def test_passes_when_target_does_not_own_it(self) -> None:
        """対象が持っていなければ成立する (例: 武器を持っていない相手にだけ)。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM,
            target_item_spec_id=FLINT,
        )
        assert _check(cond, target_owned=frozenset({DRIFTWOOD})) == (True, None)

    @pytest.mark.parametrize("reason", ["missing", "unsupported"])
    def test_evaluation_failure_is_not_inverted_to_satisfied(self, reason: str) -> None:
        """所持評価不能は「持っていない」へ反転せず、即時停止する。"""
        common = MagicMock()
        failed = MagicMock()
        common.evaluate.return_value = (
            PredicateResult.context_missing(
                failed_predicate=failed,
                failed_path=(),
                required_context={"owned_item_spec_ids"},
            )
            if reason == "missing"
            else PredicateResult.unsupported(failed_predicate=failed, failed_path=())
        )
        condition = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM,
            target_item_spec_id=FLINT,
        )
        interaction = InteractionDef(
            action_name="take",
            display_label="奪う",
            preconditions=(condition,),
            effects=(),
        )

        with pytest.raises(ScenarioPredicateEvaluationException):
            SpotInteractionService(predicate_evaluator=common).can_interact(
                interaction,
                None,
                frozenset(),
                frozenset(),
                target_owned_item_spec_ids=frozenset({DRIFTWOOD}),
            )

    def test_fails_when_target_owns_it(self) -> None:
        """対象が持っていれば不成立。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_NO_ITEM,
            target_item_spec_id=FLINT,
        )
        ok, _ = _check(cond, target_owned=frozenset({FLINT}))
        assert ok is False


class TestRuntimeItemSelectionEffect:
    """奪う品目を ``interaction_parameters`` から決める。"""

    def _apply(self, effect: InteractionEffect, params):
        return WorldGraphEffectService().apply_effects(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=[effect],
            world_flags=frozenset(),
            interaction_parameters=params,
        )

    @pytest.mark.parametrize(
        "effect_type", [InteractionEffectTypeEnum.GIVE_ITEM, InteractionEffectTypeEnum.REMOVE_ITEM]
    )
    @pytest.mark.parametrize(("key", "value", "fixed"), [("item_spec_id", 7, None), ("chosen_item", 8, 7)])
    def test_transfer_reads_spec_id_from_named_parameter(self, effect_type, key, value, fixed) -> None:
        """GIVE/REMOVEは宣言された任意キーの品目を選び、固定品目より実行時指定を優先する。"""
        parameters = {"item_spec_id_parameter": key}
        if fixed is not None:
            parameters["item_spec_id"] = fixed
        effect = InteractionEffect(effect_type=effect_type, parameters=parameters, target=EffectTarget.ACTOR)
        result = self._apply(effect, {"item_spec_id": 7, key: value})
        expected = (ItemSpecId.create(value),)
        assert result.item_spec_ids_to_grant == (expected if effect_type is InteractionEffectTypeEnum.GIVE_ITEM else ())
        assert result.item_spec_ids_to_remove == (
            expected if effect_type is InteractionEffectTypeEnum.REMOVE_ITEM else ()
        )

    def test_fixed_item_spec_id_still_works(self) -> None:
        """``item_spec_id`` を直書きする既存の書き方は変わらない。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 8},
            target=EffectTarget.ACTOR,
        )
        result = self._apply(effect, None)
        assert [s.value for s in result.item_spec_ids_to_grant] == [8]

    @pytest.mark.parametrize(
        "effect_type", [InteractionEffectTypeEnum.GIVE_ITEM, InteractionEffectTypeEnum.REMOVE_ITEM]
    )
    def test_missing_named_parameter_raises_instead_of_granting_nothing(self, effect_type) -> None:
        """参照するキーが無いのに黙って 0 個付与にしない。

        黙って何も渡さないと「奪ったのに何も手に入らない」が成功として返る。
        条件側 (``TARGET_HAS_ITEM``) が先に弾く前提なので、ここまで来るのは
        配線の壊れであり、明示的に落とす。
        """
        effect = InteractionEffect(
            effect_type=effect_type,
            parameters={"item_spec_id_parameter": "item_spec_id"},
            target=EffectTarget.ACTOR,
        )
        with pytest.raises(InteractionEffectValidationException, match="item_spec_id"):
            self._apply(effect, {})
