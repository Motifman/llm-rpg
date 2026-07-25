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

DRIFTWOOD = ItemSpecId.create(7)
FLINT = ItemSpecId.create(8)


def _check(cond: InteractionCondition, *, target_owned=None, params=None):
    """condition 1 件だけの interaction を評価して (ok, message) を返す。"""
    idef = InteractionDef(
        action_name="take", display_label="奪う", preconditions=(cond,), effects=()
    )
    return SpotInteractionService().can_interact(
        idef,
        None,
        frozenset(),
        frozenset(),
        interaction_parameters=params,
        target_owned_item_spec_ids=target_owned,
    )


class TestTargetHasItem:
    """``TARGET_HAS_ITEM`` は行為者ではなく対象の所持を見る。"""

    def test_passes_when_target_owns_the_fixed_item(self) -> None:
        """対象が指定アイテムを持っていれば成立する。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            target_item_spec_id=DRIFTWOOD,
        )
        assert _check(cond, target_owned=frozenset({DRIFTWOOD})) == (True, None)

    def test_fails_with_a_learnable_message_when_target_lacks_it(self) -> None:
        """対象が持っていなければ、内部エラーではなく前提条件の不成立で返る。"""
        ok, msg = _check(cond=InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            target_item_spec_id=DRIFTWOOD,
        ), target_owned=frozenset({FLINT}))
        assert ok is False
        assert msg

    def test_rejects_when_target_inventory_was_not_provided(self) -> None:
        """対象の所持が渡っていないのに対象の条件が書かれていたら拒否する。

        渡し忘れを黙って成立させると、持っていない相手から奪えてしまう。
        provider 不在を silent pass させない既存規約に合わせる。
        """
        ok, _ = _check(cond=InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            target_item_spec_id=DRIFTWOOD,
        ), target_owned=None)
        assert ok is False

    def test_reads_the_spec_id_from_interaction_parameters(self) -> None:
        """``item_spec_id_parameter_key`` を書くと、判定対象を実行時に決められる。"""
        cond = InteractionCondition(
            condition_type=InteractionConditionTypeEnum.TARGET_HAS_ITEM,
            item_spec_id_parameter_key="item_spec_id",
        )
        assert _check(
            cond,
            target_owned=frozenset({DRIFTWOOD}),
            params={"item_spec_id": 7},
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

    def test_give_item_reads_spec_id_from_named_parameter(self) -> None:
        """``item_spec_id_parameter`` を書くと、渡す品目を実行時に決められる。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id_parameter": "item_spec_id"},
            target=EffectTarget.ACTOR,
        )
        result = self._apply(effect, {"item_spec_id": 7})
        assert [s.value for s in result.item_spec_ids_to_grant] == [7]

    def test_fixed_item_spec_id_still_works(self) -> None:
        """``item_spec_id`` を直書きする既存の書き方は変わらない。"""
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id": 8},
            target=EffectTarget.ACTOR,
        )
        result = self._apply(effect, None)
        assert [s.value for s in result.item_spec_ids_to_grant] == [8]

    def test_missing_named_parameter_raises_instead_of_granting_nothing(self) -> None:
        """参照するキーが無いのに黙って 0 個付与にしない。

        黙って何も渡さないと「奪ったのに何も手に入らない」が成功として返る。
        条件側 (``TARGET_HAS_ITEM``) が先に弾く前提なので、ここまで来るのは
        配線の壊れであり、明示的に落とす。
        """
        effect = InteractionEffect(
            effect_type=InteractionEffectTypeEnum.GIVE_ITEM,
            parameters={"item_spec_id_parameter": "item_spec_id"},
            target=EffectTarget.ACTOR,
        )
        with pytest.raises(Exception):
            self._apply(effect, {})
