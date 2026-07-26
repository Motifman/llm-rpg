"""追放を死と区別しつつ、「退場したか」は 1 か所で答えることを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md §6.2) の PR 5。

## なぜ EJECTED を足すのか

分析で「殺されたのか追放されたのか」を区別したい。それ以上に、陣営の勝敗
条件 (#848) が「DEAD 以外は生存」で数えているため、**追放を DEAD に混ぜずに
足しただけだと、追放された相手が生存側へ回り、陣営の全滅が永久に成立しない**。

## なぜ述語をメンバに持たせるのか

`is PlayerOutcomeEnum.DEAD` を直接見ている箇所が本番コードに 4 つあった
(表示 / give_item の可否 / tend_to_player の可否 / 陣営の生存数)。すべて
「もう盤上に居ないか」を聞いているのに、**enum メンバを足すと全部が黙って
取りこぼす**。

`is_eliminated` を enum 側に持たせ、全メンバが値を宣言していることをテストで
要求する。次にメンバを足す人は、退場扱いにするかを必ず決めることになる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum


class TestEjectedIsItsOwnOutcome:
    """追放は死と区別できる。"""

    def test_ejected_exists(self) -> None:
        """EJECTED という終局がある。"""
        assert PlayerOutcomeEnum.EJECTED.value == "EJECTED"

    def test_ejected_is_not_dead(self) -> None:
        """DEAD とは別の値である (分析で読み分けたい)。"""
        assert PlayerOutcomeEnum.EJECTED is not PlayerOutcomeEnum.DEAD

    def test_ejected_is_resolved(self) -> None:
        """終局状態として扱われる (再遷移しない)。"""
        assert PlayerOutcomeEnum.EJECTED.is_resolved is True

    def test_ejected_has_its_own_label(self) -> None:
        """表示も死亡と分かれている。

        「死亡」と出ると、追放された相手を殺されたと誤読する。
        """
        assert (
            PlayerOutcomeEnum.EJECTED.display_label
            != PlayerOutcomeEnum.DEAD.display_label
        )


class TestEliminationPredicate:
    """「もう盤上に居ないか」を enum が答える。"""

    @pytest.mark.parametrize(
        "outcome",
        [PlayerOutcomeEnum.DEAD, PlayerOutcomeEnum.EJECTED],
        ids=lambda o: o.value,
    )
    def test_removed_outcomes_are_eliminated(self, outcome) -> None:
        """殺された相手と追放された相手は退場扱い。"""
        assert outcome.is_eliminated is True

    @pytest.mark.parametrize(
        "outcome",
        [
            PlayerOutcomeEnum.UNRESOLVED,
            PlayerOutcomeEnum.RESCUED,
            PlayerOutcomeEnum.STRANDED,
        ],
        ids=lambda o: o.value,
    )
    def test_others_are_not_eliminated(self, outcome) -> None:
        """未確定・救助・取り残されは退場ではない。

        RESCUED と STRANDED は盤から降りてはいるが、**力ずくで排除された
        わけではない**。陣営の全滅判定で「殺された」と同じに数えると、
        救助された仲間の数だけ全滅が早まる。
        """
        assert outcome.is_eliminated is False


class TestEveryMemberDeclaresElimination:
    """全メンバが is_eliminated を持つ。

    ここが無いと、メンバを足した人が退場扱いを決めないまま通せる。
    既定値に落ちた新メンバは、陣営の生存数に**黙って混ざる**。
    """

    @pytest.mark.parametrize(
        "outcome", list(PlayerOutcomeEnum), ids=lambda o: o.value
    )
    def test_predicate_is_a_bool(self, outcome) -> None:
        """どのメンバでも真偽値が返る (例外にならない)。"""
        assert isinstance(outcome.is_eliminated, bool)

    def test_at_least_one_member_is_eliminated(self) -> None:
        """述語が全部 False に潰れていない。

        実装を `return False` に縮めても上のテストは通ってしまう。
        """
        assert any(o.is_eliminated for o in PlayerOutcomeEnum)

    def test_at_least_one_member_is_not(self) -> None:
        """逆に全部 True にも潰れていない。"""
        assert any(not o.is_eliminated for o in PlayerOutcomeEnum)
