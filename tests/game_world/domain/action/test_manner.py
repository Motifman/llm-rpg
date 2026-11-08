from __future__ import annotations

from ai_rpg_world.game_world.domain.action.manner import Openly, Stealthily


def _never_called() -> bool:
    raise AssertionError("openly done acts must not draw whether someone notices")


class TestMannerNoticedWhen:
    """Manner.noticed_when が、公然の行為はいつも気づかれ、こっそりの行為は気づくかの判定に任せることを保証する。"""

    def test_an_open_act_is_always_noticed_without_checking(self) -> None:
        """Openly は判定を呼ばずに真を返す。偶然を引かないため。"""
        assert Openly().noticed_when(_never_called) is True

    def test_a_stealthy_act_is_noticed_only_when_the_check_says_so(self) -> None:
        """Stealthily は判定の結果をそのまま返す。"""
        assert Stealthily().noticed_when(lambda: True) is True
        assert Stealthily().noticed_when(lambda: False) is False
