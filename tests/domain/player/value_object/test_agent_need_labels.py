"""欲求の表示上の呼び名の表が、`NeedType` 全件を持ち、表に無い欲求で黙って別の呼び名に倒れないことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType


def _need(need_type: NeedType, value: int, *, max_value: int = 100) -> AgentNeed:
    return AgentNeed(need_type=need_type, value=value, max_value=max_value)


class TestTheDisplayLabelTableCoversEveryNeedType:
    """表示上の呼び名の表は `NeedType` 全件を持つ。

    以前は ``"空腹" if need_type == HUNGER else "疲労"`` の 2 分岐で、**HUNGER 以外を
    全部「疲労」と表示していた**。NeedType が 2 つしかないから偶然正しかっただけで、
    渇き (THIRST) を足したら「疲労: 危険」と出る。
    """

    def test_no_need_type_is_missing_its_label(self) -> None:
        """`NeedType` 全件に呼び名がある。"""
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        missing = sorted(n.name for n in NeedType if n not in _NEED_LABELS)

        assert missing == [], missing

    def test_every_need_type_describes_with_its_own_label(self) -> None:
        """どの欲求も自分の呼び名で表示される。

        2 分岐が戻ったら (= 既定で「疲労」に倒れたら) ここで落ちる。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        for need_type in NeedType:
            described = _need(need_type, 90).describe()
            assert described.startswith(_NEED_LABELS[need_type]), (
                need_type.name,
                described,
            )

    def test_an_unregistered_need_type_fails_loudly(self) -> None:
        """表に無い欲求は**黙って別の呼び名へ倒れず**、その場で落ちる。

        これが 2 分岐との決定的な違い。``"空腹" if HUNGER else "疲労"`` は表に無い
        欲求を**静かに「疲労」と表示する**。表引きなら `KeyError` で落ちる。

        `NeedType` が 2 つしかない今、2 分岐へ戻す変異は挙動が同じなので他の試験
        では捕まえられない (実際に変異で確認した: 25 passed)。**倒れ方の違い**だけが
        検出できる差である。

        ここで落ちるのは「新しい欲求を足した人が、呼び名を書くまで気づく」形。
        表示に嘘が出るより、起動時に落ちる方がよい。
        """

        class _Unregistered:
            name = "THIRST"

        need = AgentNeed(
            need_type=_Unregistered(),  # type: ignore[arg-type]
            value=90,
            max_value=100,
        )

        with pytest.raises(KeyError):
            need.describe()

    def test_the_labels_are_distinct(self) -> None:
        """呼び名が欲求ごとに違う。

        同じ呼び名を 2 つの欲求に付けると、表示から区別できなくなる。
        """
        from ai_rpg_world.domain.player.value_object.agent_need import _NEED_LABELS

        labels = list(_NEED_LABELS.values())

        assert len(set(labels)) == len(labels), labels
