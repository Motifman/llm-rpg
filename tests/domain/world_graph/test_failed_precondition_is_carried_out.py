"""どの前提条件で落ちたかが、判定側から呼び出し側へ運ばれることを保証する。

## なぜこの試験が要るか

判定した瞬間は条件の種別・対象・要求値を確実に知っているのに、以前は
``(False, failure_message)`` の文字列だけを返して**型を捨てていた**。そして
application 層がその日本語を部分一致検索して型を当て直していた (#380)。

捨てた情報を渡せば推測は要らない。ただし「渡す」経路自体が抜けても、分類器は
``None`` を受けて ``MISSING_PREREQUISITE`` へ倒れるだけで**例外にならない**。

実際に変異で確かめた: ``return False, msg, cond`` を ``return False, msg, None`` に
変えても、分類器と executor の試験は **39 passed で素通りした**。分類器の論理を
いくら固めても、材料が届かなければ意味がない。

だから domain 側の受け渡しをここで直接見る。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

_BUSH = SpotObjectId.create(11)


def _bush(*, available: bool) -> SpotObject:
    return SpotObject(
        object_id=_BUSH,
        name="茂み",
        description="実がなる。",
        object_type=SpotObjectTypeEnum.OTHER,
        state={"available": available},
        interactions=(),
    )


def _state_condition() -> InteractionCondition:
    return InteractionCondition(
        condition_type=InteractionConditionTypeEnum.OBJECT_STATE,
        target_object_id=_BUSH,
        required_state={"available": True},
        failure_message="ここの実はもう採った。",
    )


def _item_condition() -> InteractionCondition:
    return InteractionCondition(
        condition_type=InteractionConditionTypeEnum.HAS_ITEM,
        target_item_spec_id=None,
        failure_message="道具がない。",
    )


def _interaction(*conditions: InteractionCondition) -> InteractionDef:
    return InteractionDef(
        action_name="gather",
        display_label="採る",
        preconditions=tuple(conditions),
        effects=(),
    )


class TestEvaluatePreconditionsReportsWhichOneFailed:
    """`evaluate_preconditions` が落ちた条件そのものを返す。"""

    def test_the_failing_condition_is_returned(self) -> None:
        """落ちた条件が 3 つ目の戻り値として返る。"""
        condition = _state_condition()

        ok, reason, failed = SpotInteractionService().evaluate_preconditions(
            _interaction(condition),
            _bush(available=False),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        assert ok is False
        assert failed is condition

    def test_the_first_failing_condition_is_returned(self) -> None:
        """複数の条件があるとき、最初に落ちたものが返る。

        `failure_message` も最初に落ちたものが使われるので、区分と文が同じ条件を
        指していなければ助言と説明が食い違う。
        """
        first = _state_condition()
        second = _item_condition()

        _ok, reason, failed = SpotInteractionService().evaluate_preconditions(
            _interaction(first, second),
            _bush(available=False),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        assert failed is first
        assert reason == first.failure_message

    def test_nothing_is_returned_when_all_conditions_pass(self) -> None:
        """すべて通ったときは条件を返さない。"""
        ok, reason, failed = SpotInteractionService().evaluate_preconditions(
            _interaction(_state_condition()),
            _bush(available=True),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        assert (ok, reason, failed) == (True, None, None)


class TestCanInteractStaysCompatible:
    """`can_interact` の戻り値は 2 要素のまま。"""

    def test_it_still_returns_two_values(self) -> None:
        """`can_interact` は (成否, 理由) を返す。

        #380 で richer な `evaluate_preconditions` を新設したが、`can_interact` は
        テストを含め 64 箇所から呼ばれている。**戻り値を増やすと呼び出し側が全部
        壊れる**ので、こちらは委譲のまま維持する。
        """
        result = SpotInteractionService().can_interact(
            _interaction(_state_condition()),
            _bush(available=False),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        assert len(result) == 2
        assert result[0] is False

    def test_it_agrees_with_the_richer_method(self) -> None:
        """委譲先と成否・理由が一致する。"""
        service = SpotInteractionService()
        args = (_interaction(_state_condition()), _bush(available=False))
        kwargs = {"owned_item_spec_ids": frozenset(), "world_flags": frozenset()}

        ok, reason = service.can_interact(*args, **kwargs)
        rich_ok, rich_reason, _failed = service.evaluate_preconditions(*args, **kwargs)

        assert (ok, reason) == (rich_ok, rich_reason)


class TestTheExceptionCarriesTheCondition:
    """`execute_interaction` が投げる例外に条件が載る。"""

    def test_the_exception_exposes_the_failed_condition(self) -> None:
        """`InteractionNotAllowedException.failed_condition` に条件が載る。

        application 層はこれを読んで区分する。載らないと `None` になり、すべて
        「前提が足りない」へ倒れて「待てば戻る」が判別できなくなる。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        condition = _state_condition()
        interaction = _interaction(condition)
        obj = SpotObject(
            object_id=_BUSH,
            name="茂み",
            description="実がなる。",
            object_type=SpotObjectTypeEnum.OTHER,
            state={"available": False},
            interactions=(interaction,),
        )

        interior = SpotInterior(
            sub_locations=(),
            objects=(obj,),
            ground_items=(),
            discoverable_items=(),
        )

        with pytest.raises(InteractionNotAllowedException) as exc_info:
            SpotInteractionService().execute_interaction(
                interior,
                _BUSH,
                "gather",
                frozenset(),
                frozenset(),
            )

        assert exc_info.value.failed_condition is condition

    def test_a_bare_raise_still_works(self) -> None:
        """条件を渡さない従来の raise もそのまま動く。

        11 箇所の既存 raise を書き換えずに済ませるための互換性。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            InteractionNotAllowedException,
        )

        exc = InteractionNotAllowedException("その道具を持っていない。")

        assert str(exc) == "その道具を持っていない。"
        assert exc.failed_condition is None
