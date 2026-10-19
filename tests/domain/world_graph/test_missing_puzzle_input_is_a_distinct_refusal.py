"""番号を入れる操作で、入力が無い断りと番号違いの断りを、別の例外で投げ分けることを保証する (#1607)。

application 層は `InteractionParameterMissingException` のときだけ、同じ場所の他の人へ
失敗の観測を出さない (design_decisions D1607)。物体の経路と道具に宿る操作の経路の
両方で投げ分ける。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionParameterMissingException,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

_SAFE = SpotObjectId.create(7)
_OPEN = InteractionDef(
    action_name="open_safe",
    display_label="番号を合わせて開ける",
    preconditions=(
        InteractionCondition(
            condition_type=InteractionConditionTypeEnum.PUZZLE_INPUT_MATCH,
            puzzle_input_key="code",
            required_state={"answer": "1907"},
            failure_message="扉はびくともしない。",
        ),
    ),
    effects=(),
)
_MISSING = [
    pytest.param(None, id="no_parameters"),
    pytest.param({"text": "1907"}, id="other_key"),
    pytest.param({"code": ""}, id="empty"),
    pytest.param({"code": "   "}, id="blank"),
]


def _interior() -> SpotInterior:
    safe = SpotObject(
        object_id=_SAFE,
        name="金庫",
        description="d",
        object_type=SpotObjectTypeEnum.OTHER,
        state={},
        interactions=(_OPEN,),
    )
    return SpotInterior((), (safe,), (), ())


def _open_the_safe(parameters):
    return SpotInteractionService().execute_interaction(
        _interior(), _SAFE, "open_safe", frozenset(), frozenset(),
        interaction_parameters=parameters,
    )


def _open_by_a_tool(parameters):
    return SpotInteractionService().execute_declared_interaction(
        _interior(), _OPEN, frozenset(), frozenset(),
        interaction_parameters=parameters,
    )


@pytest.mark.parametrize("attempt", [_open_the_safe, _open_by_a_tool])
class TestMissingPuzzleInput:
    """入力が無いときと番号違いのときに投げる例外の型を、物体の経路と道具の経路の両方で保証する。"""

    @pytest.mark.parametrize("parameters", _MISSING)
    def test_missing_or_blank_code_raises_parameter_missing(self, attempt, parameters) -> None:
        """"code" が無いか、空文字か、空白だけのときは InteractionParameterMissingException を投げ、文に "code" を含む。"""
        with pytest.raises(InteractionParameterMissingException) as caught:
            attempt(parameters)

        assert '"code"' in str(caught.value)

        assert caught.value.failed_condition is _OPEN.preconditions[0]

    def test_wrong_code_raises_the_plain_refusal(self, attempt) -> None:
        """"code" に違う番号を入れたときは、親の InteractionNotAllowedException をシナリオの文で投げる。"""
        with pytest.raises(InteractionNotAllowedException) as caught:
            attempt({"code": "0000"})

        assert type(caught.value) is InteractionNotAllowedException
        assert str(caught.value) == "扉はびくともしない。"
