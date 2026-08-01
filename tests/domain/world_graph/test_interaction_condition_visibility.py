"""前提条件の種類ごとに、満たせないときの扱いが宣言されていることを保証する。

## なぜ要るか

満たしていない条件は既定では「いまできない: 〜」として候補に残る。役割の
ような**伏せた属性に依存する条件だけ**は、存在ごと隠す必要がある。実 run で
crew の候補一覧に keeper 専用の偽装版が並び、「この作業には偽装版がある」が
全員に伝わっていた。

新しい条件を足した人が扱いを決めずに済むと、**秘匿すべき条件が既定の
「見せる」に落ちて静かに漏れる**。ここで足し忘れを止める。

`interaction_condition_type.py` に 1 つ足したら、このテストが落ちる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_visibility import (
    CONDITION_VISIBILITY,
    ConditionVisibility,
    is_hidden,
)


class TestEveryConditionTypeIsClassified:
    """すべての条件が、どちらの扱いか宣言されている。"""

    def test_no_condition_type_is_left_undeclared(self) -> None:
        """宣言漏れの条件が無い。

        落ちたら、足した条件が**伏せた属性に依存するか**を決めてから
        `CONDITION_VISIBILITY` に書く。どちらでもよいから片方に書く、では
        なく「これを満たせない人に、条件の存在を知らせてよいか」を考える。
        """
        undeclared = sorted(
            c.value for c in InteractionConditionTypeEnum if c not in CONDITION_VISIBILITY
        )

        assert not undeclared, f"扱いが宣言されていない条件: {undeclared}"

    def test_the_map_does_not_name_conditions_that_vanished(self) -> None:
        """消えた条件が表に残らない。

        残ると、表を読んだ人が実在しない条件を扱っているつもりになる。
        """
        known = set(InteractionConditionTypeEnum)
        stale = sorted(c.value for c in CONDITION_VISIBILITY if c not in known)

        assert not stale, f"実在しない条件が表に残っています: {stale}"


class TestRoleConditionsAreHidden:
    """誰が何者かに依存する条件は隠す。"""

    @pytest.mark.parametrize(
        "condition_type",
        [
            InteractionConditionTypeEnum.PLAYER_STATE_IS,
            InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS,
        ],
    )
    def test_free_state_conditions_are_hidden(self, condition_type) -> None:
        """自由 state による条件は隠す側。

        役割 (role=keeper) のような伏せた属性がここに入る。
        """
        assert is_hidden(condition_type) is True


class TestPhysicalConditionsStayVisible:
    """物理・環境の条件は理由を見せる。"""

    @pytest.mark.parametrize(
        "condition_type",
        [
            InteractionConditionTypeEnum.HAS_ITEM,
            InteractionConditionTypeEnum.OBJECT_STATE,
            InteractionConditionTypeEnum.WEATHER_IS,
            InteractionConditionTypeEnum.TIME_OF_DAY_IS,
        ],
    )
    def test_they_are_not_hidden(self, condition_type) -> None:
        """隠さない。

        隠しすぎると「説明は操作を誘うのに候補が空」になり、存在しない
        操作名を発明される (`_interaction_blocking_hints` の判断)。
        """
        assert is_hidden(condition_type) is False


class TestUnknownDefaultsToHiding:
    """宣言の無い条件は隠す側に倒す。"""

    def test_an_unmapped_condition_is_treated_as_hidden(self) -> None:
        """表に無い条件は隠す。

        既定を「見せる」にすると、秘匿すべき条件を足した人が気づかない
        まま漏らす。逆に倒せば、足し忘れは「候補が出ない」として作者に
        見える。**静かに漏れるより、目に見えて欠ける方を選ぶ。**
        """

        class _Unknown:
            pass

        assert is_hidden(_Unknown()) is True

    def test_the_default_is_not_reachable_in_practice(self) -> None:
        """とはいえ、実在する条件はすべて宣言済み。

        既定に頼るのは書き忘れたときだけ、という状態を保つ。
        """
        assert all(c in CONDITION_VISIBILITY for c in InteractionConditionTypeEnum)
        assert set(CONDITION_VISIBILITY.values()) <= set(ConditionVisibility)
