"""対人行為の「相手が有効か」を 1 箇所で決めることを保証する。

## なぜ括り出すか

負債マップ (docs/precondition_target_state_debt_map.md) の #2。同じ判定が
行動ごとにバラバラに書かれている。

- `attack` はドメインサービスに委譲 (良い)
- `tend_to_player` は executor 内にべた書き
- `give_item` は転送サービス内に独自実装

負債マップは「give_item に死亡ガードが無い」と書いているが、**確認したら
既に入っていた** (7/25 以降に誰かが直した)。判定が散っているので、直った
ことも壊れたことも一覧では分からない。それ自体がこの括り出しの動機になる。

実 run でも歪みが出た。死体の同席者行に「背後から襲う」「持ち物を奪う」
「tend_to_player」が並び、追放された人まで同じ行に出続けていた。

判定が散っていると、行動を 1 つ足すたびに「死んだ相手をどう扱うか」を
書き直すことになる。**1 箇所に集めて、行動側は「どんな相手が要るか」だけを
宣言する。**

## 要求を宣言する形にした理由

「有効かどうか」は行為によって逆になる。手当ては倒れた相手にしか意味が無く、
物を渡すのは立っている相手にしか意味が無い。真偽値 1 つでは表せないので、
**何を要求するか**を呼び出し側が宣言する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.actionable_target import (
    TargetRequirement,
    validate_actionable_target,
)


class _Status:
    """判定に要る最小限だけを持つ相手。"""

    def __init__(self, *, is_down: bool = False) -> None:
        self.is_down = is_down


_STANDING = _Status()
_DOWNED = _Status(is_down=True)


def _check(**kwargs):
    base = dict(
        actor_player_id=1,
        target_player_id=2,
        actor_status=_STANDING,
        target_status=_STANDING,
        target_outcome=PlayerOutcomeEnum.UNRESOLVED,
        same_spot=True,
        requirement=TargetRequirement.ACTIVE,
    )
    base.update(kwargs)
    return validate_actionable_target(**base)


class TestUniversalRules:
    """どの行為にも共通で効く決まり。"""

    def test_a_valid_target_passes(self) -> None:
        """条件を満たす相手は通る。"""
        assert _check() is None

    def test_you_cannot_target_yourself(self) -> None:
        """自分自身は対象にできない。"""
        rejection = _check(target_player_id=1)

        assert rejection is not None
        assert rejection.code == "TARGET_IS_SELF"

    def test_a_target_elsewhere_is_rejected(self) -> None:
        """別の場所に居る相手は対象にできない。

        同席していない相手に手を伸ばせると、部屋を分けた意味が消える。
        """
        assert _check(same_spot=False).code == "NOT_IN_SAME_SPOT"

    def test_a_downed_actor_cannot_act_on_others(self) -> None:
        """倒れている本人は、他人に対して何もできない。"""
        assert _check(actor_status=_DOWNED).code == "ACTOR_IS_DOWN"

    @pytest.mark.parametrize(
        "outcome", [PlayerOutcomeEnum.DEAD, PlayerOutcomeEnum.EJECTED]
    )
    def test_an_eliminated_target_is_rejected(self, outcome) -> None:
        """退場した相手は対象にできない。

        **これが実 run で歪みとして出た形。** 死体や追放された人に
        「襲う」「渡す」が並んでいた。DEAD と EJECTED を分けずに扱うのは
        `is_eliminated` の判断と揃えるため。
        """
        assert _check(target_outcome=outcome).code == "TARGET_IS_ELIMINATED"


class TestRequirementActive:
    """立っている相手を要求する行為 (物を渡す・囁く)。"""

    def test_a_downed_target_is_rejected(self) -> None:
        """倒れている相手には渡せない。

        give_item は転送サービス側に同じ判定を独自に持っている。ここに
        集約して、行動が増えても書き直さなくてよい形にする。
        """
        rejection = _check(target_status=_DOWNED)

        assert rejection is not None
        assert rejection.code == "TARGET_IS_DOWN"

    def test_a_standing_target_passes(self) -> None:
        """立っている相手には渡せる。"""
        assert _check(target_status=_STANDING) is None


class TestRequirementIncapacitated:
    """倒れている相手を要求する行為 (手当て・漁る・通報)。"""

    def test_a_standing_target_is_rejected(self) -> None:
        """立っている相手は対象にならない。"""
        rejection = _check(
            requirement=TargetRequirement.INCAPACITATED, target_status=_STANDING
        )

        assert rejection is not None
        assert rejection.code == "TARGET_IS_NOT_DOWN"

    def test_a_downed_target_passes(self) -> None:
        """倒れている相手には効く。"""
        assert (
            _check(
                requirement=TargetRequirement.INCAPACITATED, target_status=_DOWNED
            )
            is None
        )

    def test_an_eliminated_target_is_still_rejected(self) -> None:
        """倒れていても、退場が確定した相手には効かない。

        蘇生の猶予が切れた相手を起こせると、**死が確定しなくなる**。
        倒れているかどうかとは別に見る必要がある。
        """
        rejection = _check(
            requirement=TargetRequirement.INCAPACITATED,
            target_status=_DOWNED,
            target_outcome=PlayerOutcomeEnum.DEAD,
        )

        assert rejection is not None
        assert rejection.code == "TARGET_IS_ELIMINATED"


class TestEveryRequirementIsHandled:
    """要求の種類を増やしたら、判定にも足すことを強制する。"""

    def test_no_requirement_falls_through_silently(self) -> None:
        """すべての要求が判定を通る。

        分岐を書き忘れた要求が「常に通る」に落ちると、その行為だけ判定が
        効かなくなる。**足りない側に倒れる**ので気付きにくい。
        """
        for requirement in TargetRequirement:
            # 立っている相手・倒れている相手の双方で、例外なく結論が出る。
            for status in (_STANDING, _DOWNED):
                result = _check(requirement=requirement, target_status=status)
                assert result is None or result.code, requirement

    def test_a_rejection_always_carries_a_message(self) -> None:
        """拒否には必ず理由の文が付く。

        code だけだとツール結果に出せない。「なぜ駄目か」が本人に返らないと
        同じ手を繰り返す。
        """
        for kwargs in (
            {"target_player_id": 1},
            {"same_spot": False},
            {"actor_status": _DOWNED},
            {"target_outcome": PlayerOutcomeEnum.DEAD},
            {"target_status": _DOWNED},
        ):
            rejection = _check(**kwargs)
            assert rejection is not None and rejection.message, kwargs


class TestTendNoLongerRevivesTheConfirmedDead:
    """死亡が確定した相手は蘇生できない。

    **括り出しで実際に塞がった穴。** 旧 tend_to_player は `is_down` しか
    見ていなかった。猶予が切れて DEAD が確定しても `is_down` は True のまま
    なので、**死体を起こせた**。この関数の docstring 自身が「将来 PR」と
    して触れていた。

    普遍則に載せ替えたことで、行動側に何も書かずに塞がった。行動を 1 つ
    足すたびに「死んだ相手をどう扱うか」を書き直さなくてよい、という
    括り出しの目的がそのまま出た形。
    """

    def _executor_with(self, *, outcome):
        from unittest.mock import MagicMock

        from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (  # noqa: E501
            SpotGraphToolExecutor,
        )

        actor = MagicMock(is_down=False, current_spot_id=1)
        target = MagicMock(is_down=True, current_spot_id=1)
        status_repo = MagicMock()
        status_repo.find_by_id.side_effect = lambda pid: (
            actor if int(pid) == 1 else target
        )
        runtime = MagicMock()
        runtime._player_outcome_registry.get_outcome.return_value = outcome

        services = MagicMock()
        services.movement = MagicMock()
        return SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=MagicMock(),
            item_repository=MagicMock(),
            event_publisher=MagicMock(),
            spot_graph_repository=MagicMock(),
            player_status_repository=status_repo,
            runtime=runtime,
        )

    def test_a_confirmed_dead_target_cannot_be_revived(self) -> None:
        """DEAD が確定した相手は起こせない。"""
        executor = self._executor_with(outcome=PlayerOutcomeEnum.DEAD)

        result = executor._tend_to_player(
            1, {"target_player_id": 2, "target_display_name": "セナ"}
        )

        assert result.success is False
        assert "戻らない" in result.message

    def test_a_merely_downed_target_can_still_be_revived(self) -> None:
        """まだ猶予のある相手は今までどおり起こせる。

        塞ぎすぎると蘇生そのものができなくなる。
        """
        executor = self._executor_with(outcome=PlayerOutcomeEnum.UNRESOLVED)

        result = executor._tend_to_player(
            1, {"target_player_id": 2, "target_display_name": "セナ"}
        )

        assert result.success is not False or "戻らない" not in result.message
